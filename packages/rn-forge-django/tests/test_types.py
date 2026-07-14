import pytest

from rn_forge.django.models import BaseEnum, Status

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class Color(BaseEnum):
    Red = "R"
    Green = "G"
    Blue = "B"


# ---------------------------------------------------------------------------
# BaseEnum — lookup dict
# ---------------------------------------------------------------------------


class TestBaseEnumLookupDict:
    def test_lookup_dict_built_on_subclass(self) -> None:
        assert Color._lookup == {"R": "Red", "G": "Green", "B": "Blue"}

    def test_lookup_dict_independent_per_subclass(self) -> None:
        assert Status._lookup != Color._lookup

    def test_lookup_dict_not_defined_on_base(self) -> None:
        # BaseEnum has no members so __init_subclass__ is never called for it;
        # _lookup only exists on concrete subclasses.
        assert not hasattr(BaseEnum, "_lookup")


# ---------------------------------------------------------------------------
# BaseEnum — get_choices
# ---------------------------------------------------------------------------


class TestGetChoices:
    def test_returns_all_choices_unfiltered(self) -> None:
        choices = Color.get_choices()
        assert len(choices) == 3
        assert {"code": "R", "name": "Red"} in choices
        assert {"code": "G", "name": "Green"} in choices
        assert {"code": "B", "name": "Blue"} in choices

    def test_code_filter_restricts_results(self) -> None:
        choices = Color.get_choices(code_filter=["R", "B"])
        codes = {c["code"] for c in choices}
        assert codes == {"R", "B"}

    def test_name_filter_restricts_results(self) -> None:
        choices = Color.get_choices(name_filter=["Green"])
        assert choices == [{"code": "G", "name": "Green"}]

    def test_combined_filter(self) -> None:
        # code_filter and name_filter both must match
        choices = Color.get_choices(code_filter=["R", "G"], name_filter=["Green"])
        assert choices == [{"code": "G", "name": "Green"}]

    def test_empty_result_for_no_match(self) -> None:
        assert Color.get_choices(code_filter=["Z"]) == []

    def test_code_filter_none_is_unfiltered(self) -> None:
        assert len(Color.get_choices(code_filter=None)) == 3

    def test_name_filter_none_is_unfiltered(self) -> None:
        assert len(Color.get_choices(name_filter=None)) == 3

    def test_return_type_is_list_of_dicts(self) -> None:
        choices = Color.get_choices()
        assert isinstance(choices, list)
        for item in choices:
            assert isinstance(item, dict)
            assert set(item.keys()) == {"code", "name"}


# ---------------------------------------------------------------------------
# BaseEnum — lookup
# ---------------------------------------------------------------------------


class TestLookup:
    def test_valid_key_returns_dict(self) -> None:
        assert Color.lookup("R") == {"code": "R", "name": "Red"}

    def test_all_valid_keys(self) -> None:
        assert Color.lookup("G") == {"code": "G", "name": "Green"}
        assert Color.lookup("B") == {"code": "B", "name": "Blue"}

    def test_invalid_key_raises_key_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid value for Color: 'Z'"):
            Color.lookup("Z")

    def test_empty_string_raises_key_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid value for Color: ''"):
            Color.lookup("")


# ---------------------------------------------------------------------------
# Status — concrete enum
# ---------------------------------------------------------------------------


class TestStatus:
    def test_all_values_present(self) -> None:
        assert Status.Active == "A"
        assert Status.Inactive == "I"
        assert Status.Error == "E"
        assert Status.Deleted == "D"
        assert Status.Expired == "X"

    def test_get_choices_returns_five_entries(self) -> None:
        assert len(Status.get_choices()) == 5

    def test_lookup_active(self) -> None:
        assert Status.lookup("A") == {"code": "A", "name": "Active"}

    def test_lookup_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid value for Status: 'Q'"):
            Status.lookup("Q")


# ---------------------------------------------------------------------------
# Multiple independent subclasses don't bleed into each other
# ---------------------------------------------------------------------------


class TestIsolation:
    def test_two_subclasses_have_separate_lookups(self) -> None:
        class Foo(BaseEnum):
            Alpha = "1"

        class Bar(BaseEnum):
            Beta = "2"

        assert Foo._lookup == {"1": "Alpha"}
        assert Bar._lookup == {"2": "Beta"}

    def test_new_subclass_does_not_affect_color(self) -> None:
        class Extra(BaseEnum):
            X = "X"

        assert "X" not in Color._lookup
