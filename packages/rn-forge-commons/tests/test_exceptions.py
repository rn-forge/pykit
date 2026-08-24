"""Tests for rn_forge.commons.exceptions."""

import pytest

from rn_forge.commons.exceptions import AppException


class TestAppException:
    def test_basic_message(self):
        exc = AppException("something went wrong")
        assert exc.message == "something went wrong"
        assert str(exc) == "-1 | something went wrong | {}"

    def test_message_format_args(self):
        exc = AppException("value {} is invalid", 42)
        assert exc.message == "value 42 is invalid"

    def test_custom_error_code(self):
        exc = AppException("oops", error_code=404)
        assert exc.error_code == 404

    def test_error_data(self):
        exc = AppException("oops", field="name", value="")
        assert exc.error_data == {"field": "name", "value": ""}

    def test_str_includes_all_parts(self):
        exc = AppException("bad input", error_code=400, field="email")
        result = str(exc)
        assert "400" in result
        assert "bad input" in result
        assert "email" in result

    def test_repr(self):
        exc = AppException("err", error_code=1)
        r = repr(exc)
        assert "AppException" in r
        assert "error_code=1" in r

    def test_is_exception(self):
        assert issubclass(AppException, Exception)
        with pytest.raises(AppException):
            raise AppException("boom")

    def test_args_set_for_stdlib_compat(self):
        exc = AppException("hello {}", "world")
        assert exc.args == ("hello world",)


class TestAppExceptionCheck:
    def test_check_passes_on_truthy(self):
        AppException.check(True, "should not raise")
        AppException.check(1, "should not raise")
        AppException.check("non-empty", "should not raise")

    def test_check_raises_on_falsy(self):
        with pytest.raises(AppException, match="value is required"):
            AppException.check(None, "value is required")

    def test_check_raises_on_false(self):
        with pytest.raises(AppException):
            AppException.check(False, "flag must be set")

    def test_check_raises_on_empty_string(self):
        with pytest.raises(AppException):
            AppException.check("", "empty not allowed")

    def test_check_raises_subclass_instance(self):
        class MyError(AppException):
            pass

        with pytest.raises(MyError):
            MyError.check(None, "subclass error")

    def test_check_passes_kwargs_to_constructor(self):
        with pytest.raises(AppException) as exc_info:
            AppException.check(None, "bad", error_code=422, field="x")
        exc = exc_info.value
        assert exc.error_code == 422
        assert exc.error_data["field"] == "x"

    def test_check_message_format_args(self):
        with pytest.raises(AppException) as exc_info:
            AppException.check(0, "field {} has bad value {}", "age", -1)
        assert "age" in exc_info.value.message
        assert "-1" in exc_info.value.message
