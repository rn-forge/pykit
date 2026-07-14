"""Tests for rn_forge.commons.reflection."""

import inspect as stdlib_inspect

from rn_forge.commons.reflection import ReflectUtils


class TestGetFullyQualifiedName:
    def test_class(self):
        result = ReflectUtils.get_fully_qualified_name(str)
        assert result == "builtins.str"

    def test_function(self):
        def my_func():
            pass

        result = ReflectUtils.get_fully_qualified_name(my_func)
        assert "my_func" in result

    def test_instance(self):
        result = ReflectUtils.get_fully_qualified_name(42)
        assert result == "builtins.int"

    def test_instance_custom_class(self):
        class MyClass:
            pass

        obj = MyClass()
        result = ReflectUtils.get_fully_qualified_name(obj)
        assert "MyClass" in result

    def test_frame(self):
        frame = stdlib_inspect.currentframe()
        assert frame is not None
        result = ReflectUtils.get_fully_qualified_name(frame)
        assert __name__ in result
        assert "test_frame" in result

    def test_exception_instance(self):
        exc = ValueError("oops")
        result = ReflectUtils.get_fully_qualified_name(exc)
        assert result == "builtins.ValueError"

    def test_nested_class(self):
        class Outer:
            class Inner:
                pass

        result = ReflectUtils.get_fully_qualified_name(Outer.Inner)
        assert "Outer.Inner" in result


class TestGetErrorMessage:
    def test_format(self):
        exc = ValueError("bad value")
        result = ReflectUtils.get_error_message(exc)
        assert "ValueError" in result
        assert "bad value" in result
        assert " -> " in result

    def test_custom_exception(self):
        class MyError(Exception):
            pass

        exc = MyError("custom msg")
        result = ReflectUtils.get_error_message(exc)
        assert "MyError" in result
        assert "custom msg" in result


class TestInspectMethodArguments:
    def test_basic_positional(self):
        def fn(a, b, c):
            pass

        result = ReflectUtils.inspect_method_arguments(fn, (1, 2, 3), {})
        assert result == ["a=1", "b=2", "c=3"]

    def test_kwargs(self):
        def fn(x, y=10):
            pass

        result = ReflectUtils.inspect_method_arguments(fn, (5,), {"y": 20})
        assert "x=5" in result
        assert "y=20" in result

    def test_defaults_applied(self):
        def fn(x, y=99):
            pass

        result = ReflectUtils.inspect_method_arguments(fn, (1,), {})
        assert "y=99" in result

    def test_self_excluded_by_default(self):
        class MyClass:
            def method(self, value):
                pass

        obj = MyClass()
        result = ReflectUtils.inspect_method_arguments(MyClass.method, (obj, 42), {})
        names = [r.split("=")[0] for r in result]
        assert "self" not in names
        assert "value" in names

    def test_cls_excluded_by_default(self):
        class MyClass:
            @classmethod
            def make(cls, value):
                pass

        # inspect.signature on a bound classmethod already strips cls;
        # pass only the remaining positional argument
        result = ReflectUtils.inspect_method_arguments(MyClass.make, (7,), {})
        names = [r.split("=")[0] for r in result]
        assert "cls" not in names
        assert "value" in names

    def test_custom_exclude(self):
        def fn(a, b, c):
            pass

        result = ReflectUtils.inspect_method_arguments(fn, (1, 2, 3), {}, exclude=["b"])
        names = [r.split("=")[0] for r in result]
        assert "b" not in names
        assert "a" in names

    def test_include_overrides_default_exclusion(self):
        class MyClass:
            def method(self, value):
                pass

        obj = MyClass()
        result = ReflectUtils.inspect_method_arguments(
            MyClass.method, (obj, 5), {}, include=["self"]
        )
        names = [r.split("=")[0] for r in result]
        assert "self" in names

    def test_no_mutable_default_side_effects(self):
        def fn(a, b):
            pass

        ReflectUtils.inspect_method_arguments(fn, (1, 2), {}, exclude=["a"])
        # Second call should not accumulate previous exclude list
        result = ReflectUtils.inspect_method_arguments(fn, (1, 2), {})
        names = [r.split("=")[0] for r in result]
        assert "a" in names


class TestInspectVariables:
    def test_simple_variable(self):
        x = 42  # noqa: F841
        frame = stdlib_inspect.currentframe()
        result = ReflectUtils.inspect_variables("x", source_frame=frame)
        assert result == ["x=42"]

    def test_multiple_variables(self):
        alpha = "hello"  # noqa: F841
        beta = 99  # noqa: F841
        frame = stdlib_inspect.currentframe()
        result = ReflectUtils.inspect_variables("alpha, beta", source_frame=frame)
        assert "alpha=hello" in result
        assert "beta=99" in result

    def test_dot_notation_attribute(self):
        class Obj:
            name = "world"

        obj = Obj()  # noqa: F841
        frame = stdlib_inspect.currentframe()
        result = ReflectUtils.inspect_variables("obj.name", source_frame=frame)
        assert result == ["obj.name=world"]

    def test_dot_notation_deep_attribute(self):
        class Inner:
            value = "deep"

        class Outer:
            inner = Inner()

        obj = Outer()  # noqa: F841
        frame = stdlib_inspect.currentframe()
        result = ReflectUtils.inspect_variables("obj.inner.value", source_frame=frame)
        assert result == ["obj.inner.value=deep"]

    def test_dot_notation_callable(self):
        class Obj:
            def label(self):
                return "dynamic"

        obj = Obj()  # noqa: F841
        frame = stdlib_inspect.currentframe()
        result = ReflectUtils.inspect_variables("obj.label", source_frame=frame)
        assert result == ["obj.label=dynamic"]

    def test_falls_back_to_caller_frame(self):
        my_var = "present"  # noqa: F841
        # source_frame=None → falls back to this caller's frame
        result = ReflectUtils.inspect_variables("my_var", source_frame=None)
        assert result == ["my_var=present"]

    def test_spaces_in_var_names_stripped(self):
        a = 1  # noqa: F841
        b = 2  # noqa: F841
        frame = stdlib_inspect.currentframe()
        result = ReflectUtils.inspect_variables("a , b", source_frame=frame)
        assert "a=1" in result
        assert "b=2" in result

    def test_none_frame_returns_empty_list(self):
        # When an explicit None frame is passed, the method cannot find a
        # caller frame either (it uses currentframe().f_back internally),
        # but it also accepts an explicit None as source_frame.
        # Passing a frame object that has no locals would be artificial;
        # instead, we verify the documented contract: None → [].
        # We construct a true None frame scenario by calling with a dummy
        # None value, which should return [].
        #
        # NOTE: When source_frame=None the implementation falls back to the
        # caller's own frame, which *does* exist. To exercise the
        # "frame is None → return []" branch we patch currentframe to None.
        original_currentframe = stdlib_inspect.currentframe

        try:
            # Monkey-patch inspect.currentframe to return None at the point
            # inspect_variables tries to get the fallback frame.
            import inspect as _insp

            _insp.currentframe = lambda: None
            result = ReflectUtils.inspect_variables("some_var", source_frame=None)
            assert result == []
        finally:
            _insp.currentframe = original_currentframe

    def test_missing_root_variable_returns_undefined(self):
        frame = stdlib_inspect.currentframe()
        result = ReflectUtils.inspect_variables("missing.attr", source_frame=frame)
        assert result == ["missing.attr=<undefined>"]

    def test_missing_variable_returns_undefined(self):
        frame = stdlib_inspect.currentframe()
        result = ReflectUtils.inspect_variables("missing_var", source_frame=frame)
        assert result == ["missing_var=<undefined>"]
