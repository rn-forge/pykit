"""Tests for rn_forge.fastapi.read_mask."""

from typing import Any, Optional

import pytest
from assertpy import assert_that
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, computed_field

from rn_forge.fastapi import masked, read_mask_param, register_problem_handlers
from rn_forge.web import Page, ReadMask, WireModel

pytestmark = pytest.mark.unit


class Address(WireModel):
    street_name: str
    postcode: str


class Phone(WireModel):
    kind: str
    number: str


class Account(WireModel):
    id: str
    # An explicit alias that is not the camelCase of the attribute name.
    full_name: str = Field(alias="name")
    home: Optional[Address] = None
    work: Address | None = None
    phones: list[Phone] = []
    backup_phones: Optional[list[Phone]] = None
    tags: list[str] = []
    settings: dict[str, Any] = {}

    @computed_field
    @property
    def initials(self) -> str:
        return self.full_name[:1]


ACCOUNT = Account(
    id="1",
    name="Ada Lovelace",
    home=Address(street_name="Main", postcode="N1"),
    phones=[Phone(kind="home", number="1"), Phone(kind="work", number="2")],
    tags=["x"],
    settings={"theme": "dark"},
)


def app() -> FastAPI:
    app = FastAPI()
    register_problem_handlers(app)

    @app.get("/account")
    async def account(mask: ReadMask | None = Depends(read_mask_param(Account))):
        body = ACCOUNT.model_dump()
        return JSONResponse(body if mask is None else mask.apply(body))

    @app.get("/accounts")
    async def accounts(mask: ReadMask | None = Depends(read_mask_param(Account))):
        return JSONResponse(
            masked(Page[Account](items=[ACCOUNT], next_page_token=None), mask)
        )

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app())


def test_a_field_whose_alias_differs_from_its_attribute_is_selected_by_the_alias(
    client,
):
    assert_that(client.get("/account", params={"readMask": "name"}).json()).is_equal_to(
        {"name": "Ada Lovelace"}
    )


@pytest.mark.parametrize("raw", ["fullName", "full_name"])
def test_the_attribute_name_is_not_a_path_when_an_alias_replaces_it(client, raw):
    response = client.get("/account", params={"readMask": raw})

    assert_that(response.status_code).is_equal_to(400)
    assert_that(response.json()["detail"]).is_equal_to(f"Unknown readMask path '{raw}'")


@pytest.mark.parametrize("field", ["home", "work", "backupPhones"])
def test_an_optional_model_field_is_a_subtree(client, field):
    inner = "streetName" if field != "backupPhones" else "number"
    response = client.get("/account", params={"readMask": f"{field}.{inner}"})

    assert_that(response.status_code).is_equal_to(200)


def test_an_optional_model_selects_a_sub_field_and_null_stays_null(client):
    body = client.get("/account", params={"readMask": "home.streetName,work.postcode"})

    assert_that(body.json()).is_equal_to({"home": {"streetName": "Main"}, "work": None})


def test_a_list_of_models_is_a_subtree_applied_to_each_element(client):
    body = client.get("/account", params={"readMask": "phones.number"}).json()

    assert_that(body).is_equal_to({"phones": [{"number": "1"}, {"number": "2"}]})


@pytest.mark.parametrize(
    "raw", ["tags.first", "settings.theme", "initials.x", "home.streetName.x"]
)
def test_a_list_of_scalars_a_dict_a_computed_field_and_a_scalar_are_leaves(client, raw):
    response = client.get("/account", params={"readMask": raw})

    assert_that(response.status_code).is_equal_to(400)


def test_a_computed_field_is_selectable(client):
    body = client.get("/account", params={"readMask": "initials"}).json()

    assert_that(body).is_equal_to({"initials": "A"})


def test_a_blank_or_star_mask_is_the_whole_resource(client):
    whole = client.get("/account").json()

    assert_that(client.get("/account", params={"readMask": "*"}).json()).is_equal_to(
        whole
    )
    assert_that(client.get("/account", params={"readMask": ""}).json()).is_equal_to(
        whole
    )


def test_star_with_other_paths_is_a_400(client):
    response = client.get("/account", params={"readMask": "*,id"})

    assert_that(response.status_code).is_equal_to(400)
    assert_that(response.json()["detail"]).is_equal_to(
        "readMask '*' cannot be combined with other paths"
    )


def test_masked_masks_each_item_and_keeps_the_page_members(client):
    body = client.get("/accounts", params={"readMask": "id"}).json()

    assert_that(body).is_equal_to({"items": [{"id": "1"}], "nextPageToken": None})


def test_masked_without_a_mask_is_the_pages_own_body():
    page = Page[dict[str, str]](items=[{"id": "1"}], next_page_token="t", total_size=1)

    assert_that(masked(page, None)).is_equal_to(page.as_body())


def test_the_parameter_is_documented_as_read_mask():
    parameters = app().openapi()["paths"]["/account"]["get"]["parameters"]

    assert_that([p["name"] for p in parameters]).is_equal_to(["readMask"])
    assert_that(parameters[0]["required"]).is_false()


def test_a_model_that_contains_itself_stops_at_a_leaf():
    class Node(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)

        name: str
        child: "Node | None" = None

    Node.model_rebuild()
    api = FastAPI()
    register_problem_handlers(api)

    @api.get("/node")
    async def node(mask: ReadMask | None = Depends(read_mask_param(Node))):
        body = {"name": "a", "child": {"name": "b", "child": None}}
        return JSONResponse(body if mask is None else mask.apply(body))

    client = TestClient(api)

    assert_that(
        client.get("/node", params={"readMask": "child"}).status_code
    ).is_equal_to(200)
    assert_that(
        client.get("/node", params={"readMask": "child.name"}).status_code
    ).is_equal_to(400)
