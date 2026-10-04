from __future__ import annotations

import io

import pytest

django = pytest.importorskip("django")
pytest.importorskip("import_export")

import tablib  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.db import models  # noqa: E402
from import_export import fields, resources, widgets  # noqa: E402
from rest_framework import serializers  # noqa: E402
from rest_framework.test import APIRequestFactory, force_authenticate  # noqa: E402
from rest_framework.viewsets import ModelViewSet  # noqa: E402

from rn_forge.django.drf.routers import CustomMethodRouter  # noqa: E402
from rn_forge.django.drf.transfer import (  # noqa: E402
    BatchCreateMixin,
    BatchDeleteMixin,
    BatchGetMixin,
    BatchUpdateMixin,
    ResourceExportMixin,
    ResourceImportMixin,
    _indexed_errors,
)
from rn_forge.django.drf.views.base import BaseModelViewSet  # noqa: E402
from rn_forge.django.models import BaseModel, VersionedModelMixin  # noqa: E402
from rn_forge.web import EntityVersionETagCodec  # noqa: E402
from django.test import override_settings  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class Team(models.Model):
    code = models.CharField(max_length=10, unique=True)

    class Meta:
        app_label = "rn_forge_django_messaging"


class Member(models.Model):
    name = models.CharField(max_length=30)
    email = models.CharField(max_length=50, unique=True)
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.CASCADE)
    joined = models.DateField(null=True, blank=True)
    created_by = models.CharField(max_length=50, default="", blank=True)

    class Meta:
        app_label = "rn_forge_django_messaging"


class Book(VersionedModelMixin, BaseModel):
    name = models.CharField(max_length=30)

    class Meta(BaseModel.Meta):
        app_label = "rn_forge_django_messaging"


class Note(models.Model):
    name = models.CharField(max_length=30)
    updated_by = models.CharField(max_length=50, default="", blank=True)

    class Meta:
        app_label = "rn_forge_django_messaging"


@pytest.fixture(scope="module", autouse=True)
def _tables(create_tables):
    create_tables(Team, Member, Book, Note)


class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ["id", "name", "email"]


class MemberExport(resources.ModelResource):
    team = fields.Field(attribute="team__code", column_name="Team")
    email = fields.Field(attribute="email", column_name="Email")
    name = fields.Field(attribute="name", column_name="Name")
    joined = fields.Field(attribute="joined", column_name="Joined")

    class Meta:
        model = Member
        fields = ("email", "name", "team", "joined")
        export_order = fields


class MemberImport(resources.ModelResource):
    email = fields.Field(attribute="email", column_name="EMAIL")
    name = fields.Field(
        attribute="name", column_name="FNAME", widget=widgets.CharWidget()
    )
    team = fields.Field(
        attribute="team",
        column_name="TEAM",
        widget=widgets.ForeignKeyWidget(Team, field="code"),
    )

    class Meta:
        model = Member
        fields = ("email", "name", "team")
        import_id_fields = ("email",)
        skip_unchanged = True
        report_skipped = True
        clean_model_instances = True

    def before_import_row(self, row, **kwargs):
        if row.get("FNAME") == "forbidden":
            raise PermissionError(f"{kwargs['user']} may not import this row")
        row["FNAME"] = str(row.get("FNAME", "")).title()


class Members(
    ResourceExportMixin,
    ResourceImportMixin,
    BatchCreateMixin,
    BatchDeleteMixin,
    ModelViewSet,
):
    authentication_classes: list = []
    permission_classes: list = []
    queryset = Member.objects.order_by("id")
    serializer_class = MemberSerializer
    export_resource_class = MemberExport
    import_resource_class = MemberImport
    export_column_formats = {"Joined": "yyyy-mm-dd"}

    def validate_batch_create_item(self, item):
        return "blocked" if item["name"] == "blocked" else None

    def validate_batch_delete_instance(self, instance):
        return "protected" if instance.name == "protected" else None


class Lenient(Members):
    import_rollback_on_validation_errors = False


class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ["id", "name"]
        read_only_fields = ["id"]


class Books(BatchGetMixin, BatchUpdateMixin, BaseModelViewSet):
    authentication_classes: list = []
    permission_classes: list = []
    queryset = Book.objects.order_by("id")
    serializer_class = BookSerializer
    etag_codec = EntityVersionETagCodec()

    def validate_batch_update_item(self, instance, data):
        return "locked" if instance.name == "locked" else None


class StrictBooks(Books):
    batch_update_requires_if_match = True


class ScopedBooks(Books):
    def filter_queryset(self, queryset):
        return super().filter_queryset(queryset).exclude(name="hidden")


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = ["id", "name"]
        read_only_fields = ["id"]


class Notes(BatchUpdateMixin, ModelViewSet):
    authentication_classes: list = []
    permission_classes: list = []
    queryset = Note.objects.order_by("id")
    serializer_class = NoteSerializer


router = CustomMethodRouter(trailing_slash=False)
router.register("books", Books, basename="books")
router.register("strict-books", StrictBooks, basename="strict-books")
router.register("scoped-books", ScopedBooks, basename="scoped-books")
router.register("notes", Notes, basename="notes")
router.register("members", Members, basename="members")
router.register("lenient", Lenient, basename="lenient")
urlpatterns = router.urls


@pytest.fixture(autouse=True)
def _urlconf():
    with override_settings(
        ROOT_URLCONF=__name__,
        REST_FRAMEWORK={
            "EXCEPTION_HANDLER": "rn_forge.django.drf.exceptions.problem_details_exception_handler",
        },
    ):
        yield


@pytest.fixture
def team():
    return Team.objects.create(code="EAST")


@pytest.fixture
def members(team):
    Member.objects.create(name="Ada", email="ada@x.io", team=team)
    Member.objects.create(name="Bob", email="bob@x.io", team=None)


def upload(client, path, content, name="members.csv", **query):
    file = SimpleUploadedFile(
        name, content.encode() if isinstance(content, str) else content
    )
    return client.post(
        path,
        {"file": file},
        **(
            {"QUERY_STRING": "&".join(f"{k}={v}" for k, v in query.items())}
            if query
            else {}
        ),
    )


class TestExport:
    def test_csv_uses_resource_headers_and_traverses_relations(
        self, client, members
    ) -> None:
        response = client.get("/members", headers={"Accept": "text/csv"})
        assert response.status_code == 200
        assert response.headers["Content-Type"].startswith("text/csv")
        assert response.headers["Content-Disposition"].startswith(
            'attachment; filename="members.csv"'
        )
        rows = tablib.Dataset().load(response.content.decode(), format="csv")
        assert rows.headers == ["Email", "Name", "Team", "Joined"]
        assert rows[0][:3] == ("ada@x.io", "Ada", "EAST")

    def test_xlsx_applies_column_formats(self, client, members) -> None:
        import datetime

        import openpyxl

        Member.objects.filter(name="Ada").update(joined=datetime.date(2026, 1, 2))
        response = client.get("/members?format=xlsx")
        assert response.status_code == 200
        sheet = openpyxl.load_workbook(io.BytesIO(response.content)).active
        joined = sheet["D2"]
        assert joined.number_format == "yyyy-mm-dd"

    def test_json_list_is_unchanged(self, client, members) -> None:
        response = client.get("/members")
        assert response.headers["Content-Type"] == "application/json"
        assert len(response.json()) == 2

    def test_over_the_cap_is_a_422_problem_naming_the_cap(
        self, client, members
    ) -> None:
        with override_settings(RN_FORGE_DJANGO={"DRF": {"TRANSFER": {"MAX_ROWS": 1}}}):
            response = client.get("/members?format=csv")
        assert response.status_code == 422
        assert "limit of 1 rows" in response.json()["detail"]

    def test_unknown_format_is_not_offered(self, client, members) -> None:
        assert client.get("/members?format=ods").status_code == 404


class TestImport:
    def test_upserts_and_reports_counts(self, client, members, team) -> None:
        body = "EMAIL,FNAME,TEAM\nada@x.io,ada,EAST\ncy@x.io,cy,EAST\nbob@x.io,bob,\n"
        response = upload(client, "/members:import", body)
        assert response.status_code == 200
        report = response.json()
        assert (report["created"], report["updated"], report["validateOnly"]) == (
            1,
            0,
            False,
        )
        assert report["skipped"] == 2
        assert Member.objects.get(email="cy@x.io").name == "Cy"

    def test_validate_only_persists_nothing(self, client, team) -> None:
        response = upload(
            client,
            "/members:import",
            "EMAIL,FNAME,TEAM\na@x.io,a,EAST\n",
            validateOnly="true",
        )
        assert response.json() == {
            "created": 1,
            "updated": 0,
            "skipped": 0,
            "validateOnly": True,
        }
        assert not Member.objects.exists()

    def test_a_row_error_fails_everything_with_a_pointer(self, client, team) -> None:
        body = "EMAIL,FNAME,TEAM\na@x.io,a,EAST\nb@x.io,b,NOPE\n"
        response = upload(client, "/members:import", body)
        assert response.status_code == 422
        errors = response.json()["errors"]
        assert errors[0]["pointer"] == "/rows/1"
        assert "Team" in errors[0]["detail"]
        assert not Member.objects.exists()

    def test_a_field_error_points_at_the_file_column(self, client, team) -> None:
        body = f"EMAIL,FNAME,TEAM\na@x.io,{'n' * 31},EAST\n"
        response = upload(client, "/members:import", body)
        assert response.status_code == 422
        assert response.json()["errors"][0]["pointer"] == "/rows/0/FNAME"

    def test_a_hook_error_is_a_row_error(self, client, team) -> None:
        response = upload(
            client, "/members:import", "EMAIL,FNAME,TEAM\na@x.io,forbidden,EAST\n"
        )
        assert response.status_code == 422
        assert response.json()["errors"][0]["pointer"] == "/rows/0"
        assert not Member.objects.exists()

    def test_the_lenient_variant_commits_valid_rows_and_lists_errors(
        self, client, team
    ) -> None:
        body = f"EMAIL,FNAME,TEAM\na@x.io,a,EAST\nb@x.io,{'n' * 31},EAST\n"
        response = upload(client, "/lenient:import", body)
        assert response.status_code == 200
        assert response.json()["created"] == 1
        assert response.json()["errors"][0]["pointer"] == "/rows/1/FNAME"
        assert Member.objects.filter(email="a@x.io").exists()

    def test_missing_file_is_a_422(self, client) -> None:
        response = client.post("/members:import", {})
        assert response.status_code == 422
        assert response.json()["errors"] == [
            {"pointer": "/file", "detail": "This field is required."}
        ]

    def test_unsupported_extension_is_a_422(self, client) -> None:
        assert upload(client, "/members:import", "x", name="m.pdf").status_code == 422

    def test_a_corrupt_workbook_is_a_422(self, client) -> None:
        assert (
            upload(client, "/members:import", b"not a zip", name="m.xlsx").status_code
            == 422
        )

    def test_too_many_rows_is_a_422(self, client, team) -> None:
        body = "EMAIL,FNAME,TEAM\na@x.io,a,EAST\nb@x.io,b,EAST\n"
        with override_settings(RN_FORGE_DJANGO={"DRF": {"TRANSFER": {"MAX_ROWS": 1}}}):
            response = upload(client, "/members:import", body)
        assert response.status_code == 422
        assert response.json()["detail"] == "The import exceeds the limit of 1 rows."
        assert "errors" not in response.json()

    def test_import_round_trips_an_xlsx_upload(self, client, team) -> None:
        dataset = tablib.Dataset(
            ["a@x.io", "a", "EAST"], headers=["EMAIL", "FNAME", "TEAM"]
        )
        response = upload(
            client, "/members:import", dataset.export("xlsx"), name="m.xlsx"
        )
        assert response.json()["created"] == 1


class TestImportTemplate:
    def test_is_the_import_columns_and_no_rows(self, client, members) -> None:
        response = client.get("/members:importTemplate", headers={"Accept": "text/csv"})
        assert response.status_code == 200
        assert response.content.decode().split() == ["EMAIL,FNAME,TEAM"]

    def test_prefill_adds_the_filtered_rows(self, client, members) -> None:
        response = client.get("/members:importTemplate?prefill=true&format=csv")
        assert len(response.content.decode().split()) == 3

    def test_defaults_to_the_first_import_format(self, client) -> None:
        response = client.get("/members:importTemplate")
        assert response.headers["Content-Disposition"].startswith(
            'attachment; filename="import-template.csv"'
        )


class TestBatchCreate:
    def test_creates_all_and_names_the_plural(self, client) -> None:
        response = client.post(
            "/members:batchCreate",
            {
                "requests": [
                    {"name": "a", "email": "a@x.io"},
                    {"name": "b", "email": "b@x.io"},
                ]
            },
            content_type="application/json",
        )
        assert response.status_code == 200
        assert [m["name"] for m in response.json()["members"]] == ["a", "b"]

    def test_a_hook_error_is_a_403_pointing_at_the_item(self, client) -> None:
        response = client.post(
            "/members:batchCreate",
            {
                "requests": [
                    {"name": "a", "email": "a@x.io"},
                    {"name": "blocked", "email": "b@x.io"},
                ]
            },
            content_type="application/json",
        )
        assert response.status_code == 403
        assert response.json()["errors"] == [
            {"pointer": "/requests/1", "detail": "blocked"}
        ]
        assert not Member.objects.exists()

    def test_a_body_without_a_list_is_a_422(self, client) -> None:
        response = client.post(
            "/members:batchCreate", {"requests": "x"}, content_type="application/json"
        )
        assert response.status_code == 422
        assert response.json()["errors"] == [
            {"pointer": "/requests", "detail": "A non-empty list is required."}
        ]

    def test_a_missing_member_is_required(self, client) -> None:
        response = client.post(
            "/members:batchCreate", {}, content_type="application/json"
        )
        assert response.json()["errors"] == [
            {"pointer": "/requests", "detail": "This field is required."}
        ]

    def test_over_the_cap_is_a_422_without_errors(self, client) -> None:
        items = [{"name": "a", "email": "a@x.io"}, {"name": "b", "email": "b@x.io"}]
        with override_settings(RN_FORGE_DJANGO={"DRF": {"TRANSFER": {"MAX_ROWS": 1}}}):
            response = client.post(
                "/members:batchCreate",
                {"requests": items},
                content_type="application/json",
            )
        assert response.status_code == 422
        assert response.json()["detail"] == "The batch exceeds the limit of 1 rows."
        assert "errors" not in response.json()

    def test_an_invalid_item_is_a_422_pointing_at_its_field(self, client) -> None:
        response = client.post(
            "/members:batchCreate",
            {"requests": [{"name": "a", "email": "a@x.io"}, {"name": "b"}]},
            content_type="application/json",
        )
        assert response.status_code == 422
        assert response.json()["errors"][0]["pointer"] == "/requests/1/email"
        assert not Member.objects.exists()

    def test_item_errors_are_read_from_a_list_or_a_dict_keyed_by_index(self) -> None:
        field = {"email": ["required"]}
        assert _indexed_errors([{}, field]) == [(0, {}), (1, field)]
        assert _indexed_errors({1: field}) == [(1, field)]
        assert _indexed_errors({"non_field_errors": ["x"]}) == [(0, ["x"])]


class TestBatchDelete:
    def test_deletes_all(self, client, members) -> None:
        ids = list(Member.objects.values_list("id", flat=True))
        response = client.post(
            "/members:batchDelete", {"ids": ids}, content_type="application/json"
        )
        assert response.status_code == 204
        assert not Member.objects.exists()

    def test_a_protected_row_is_a_403_and_deletes_nothing(
        self, client, members
    ) -> None:
        Member.objects.filter(name="Bob").update(name="protected")
        ids = list(Member.objects.values_list("id", flat=True))
        response = client.post(
            "/members:batchDelete", {"ids": ids}, content_type="application/json"
        )
        assert response.status_code == 403
        assert Member.objects.count() == 2


def make_books(*names):
    return [Book.objects.create(name=n) for n in names]


def update(client, path, *requests):
    return client.post(
        f"{path}:batchUpdate",
        {"requests": list(requests)},
        content_type="application/json",
    )


class TestBatchGet:
    def test_returns_resources_in_request_order_with_duplicates(self, client) -> None:
        a, b = make_books("a", "b")
        response = client.get(f"/books:batchGet?ids={b.pk}&ids={a.pk}&ids={b.pk}")
        assert response.status_code == 200
        assert response.json() == {
            "books": [
                {"id": b.pk, "name": "b"},
                {"id": a.pk, "name": "a"},
                {"id": b.pk, "name": "b"},
            ]
        }

    def test_a_comma_joined_value_is_one_id(self, client) -> None:
        a, b = make_books("a", "b")
        response = client.get(f"/books:batchGet?ids={a.pk},{b.pk}")
        assert response.status_code == 404

    def test_a_scoped_out_id_is_a_404(self, client) -> None:
        (hidden,) = make_books("hidden")
        response = client.get(f"/scoped-books:batchGet?ids={hidden.pk}")
        assert response.status_code == 404
        assert response.json()["detail"] == f"Book {hidden.pk} not found"

    def test_empty_ids_are_a_400(self, client) -> None:
        response = client.get("/books:batchGet?ids=")
        assert response.status_code == 400
        assert response.json()["detail"] == "A non-empty ids parameter is required."

    def test_over_the_cap_is_a_400(self, client) -> None:
        a, b = make_books("a", "b")
        with override_settings(RN_FORGE_DJANGO={"DRF": {"TRANSFER": {"MAX_ROWS": 1}}}):
            response = client.get(f"/books:batchGet?ids={a.pk}&ids={b.pk}")
        assert response.status_code == 400
        assert response.json()["detail"] == "The batch exceeds the limit of 1 rows."


class TestBatchUpdate:
    def test_merges_each_patch_and_bumps_each_version(self, client) -> None:
        a, b = make_books("a", "b")
        response = update(
            client,
            "/books",
            {"id": str(b.pk), "patch": {"name": "b2"}, "ifMatch": f'W/"{b.pk}:1"'},
            {"id": a.pk, "patch": {"name": "a2"}},
        )
        assert response.status_code == 200
        assert response.json() == {
            "books": [{"id": b.pk, "name": "b2"}, {"id": a.pk, "name": "a2"}]
        }
        assert [x.version for x in Book.objects.order_by("id")] == [2, 2]

    def test_a_denied_item_is_a_403_and_writes_nothing(self, client) -> None:
        a, locked = make_books("a", "locked")
        response = update(
            client,
            "/books",
            {"id": a.pk, "patch": {"name": "a2"}},
            {"id": locked.pk, "patch": {"name": "x"}},
        )
        assert response.status_code == 403
        assert response.json()["errors"] == [
            {"pointer": "/requests/1", "detail": "locked"}
        ]
        assert sorted(Book.objects.values_list("name", flat=True)) == ["a", "locked"]

    def test_required_if_match_is_a_428_with_the_pointer(self, client) -> None:
        a, b = make_books("a", "b")
        response = update(
            client,
            "/strict-books",
            {"id": a.pk, "patch": {}, "ifMatch": "*"},
            {"id": b.pk, "patch": {}},
        )
        assert response.status_code == 428
        assert response.json()["errors"][0]["pointer"] == "/requests/1/ifMatch"

    def test_audit_fields_are_set_on_every_updated_row(self, client) -> None:
        a, b = make_books("a", "b")
        update(
            client,
            "/books",
            {"id": a.pk, "patch": {"name": "a2"}},
            {"id": b.pk, "patch": {"name": "b2"}},
        )
        assert {x.updated_by for x in Book.objects.all()} == {"anonymous"}

    def test_an_unversioned_model_ignores_if_match(self, client) -> None:
        note = Note.objects.create(name="n")
        response = update(
            client,
            "/notes",
            {"id": note.pk, "patch": {"name": "n2"}, "ifMatch": "junk"},
        )
        assert response.status_code == 200
        assert response.json() == {"notes": [{"id": note.pk, "name": "n2"}]}

    def test_a_scoped_out_id_is_a_404(self, client) -> None:
        (hidden,) = make_books("hidden")
        response = update(client, "/scoped-books", {"id": hidden.pk, "patch": {}})
        assert response.status_code == 404
        assert response.json()["detail"] == f"Book {hidden.pk} not found"

    def test_an_invalid_merge_is_a_422_pointing_into_the_patch(self, client) -> None:
        a, b = make_books("a", "b")
        response = update(
            client,
            "/books",
            {"id": a.pk, "patch": {"name": "ok"}},
            {"id": b.pk, "patch": {"name": None}},
        )
        assert response.status_code == 422
        assert response.json()["errors"] == [
            {
                "pointer": "/requests/1/patch/name",
                "detail": "This field may not be null.",
            }
        ]
        assert Book.objects.get(pk=a.pk).name == "a"

    @pytest.mark.parametrize(
        ("body", "detail"),
        [
            ({}, "This field is required."),
            ({"requests": []}, "A non-empty list is required."),
        ],
    )
    def test_step_one_matches_batch_create(self, client, body, detail) -> None:
        response = client.post(
            "/books:batchUpdate", body, content_type="application/json"
        )
        create = client.post(
            "/members:batchCreate", body, content_type="application/json"
        )
        assert response.status_code == create.status_code == 422
        same = {
            k: v for k, v in create.json().items() if k not in {"traceId", "instance"}
        }
        assert response.json() == {
            **same,
            "instance": "/books:batchUpdate",
            "traceId": response.json()["traceId"],
        }
        assert response.json()["errors"] == [{"pointer": "/requests", "detail": detail}]

    def test_over_the_cap_is_the_row_cap_422(self, client) -> None:
        a, b = make_books("a", "b")
        with override_settings(RN_FORGE_DJANGO={"DRF": {"TRANSFER": {"MAX_ROWS": 1}}}):
            response = update(
                client, "/books", {"id": a.pk, "patch": {}}, {"id": b.pk, "patch": {}}
            )
        assert response.status_code == 422
        assert response.json()["detail"] == "The batch exceeds the limit of 1 rows."


def test_the_schema_names_the_batch_operations() -> None:
    pytest.importorskip("drf_spectacular")
    from drf_spectacular.generators import SchemaGenerator
    from drf_spectacular.settings import patched_settings

    from rn_forge.django.drf.openapi import SPECTACULAR_SETTINGS

    with (
        override_settings(
            REST_FRAMEWORK={
                "DEFAULT_SCHEMA_CLASS": "rn_forge.django.drf.openapi.WireAutoSchema"
            }
        ),
        patched_settings(
            {
                **SPECTACULAR_SETTINGS,
                "TITLE": "t",
            }
        ),
    ):
        schema = SchemaGenerator(patterns=router.urls).get_schema(
            request=None, public=True
        )

    operations = {
        op["operationId"] for item in schema["paths"].values() for op in item.values()
    }
    assert {"booksBatchGet", "booksBatchUpdate"} <= operations
