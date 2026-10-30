import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [  # noqa: RUF012  # Django migration attribute
        migrations.swappable_dependency(settings.AUTH_USER_MODEL)
    ]

    operations = [  # noqa: RUF012  # Django migration attribute
        migrations.CreateModel(
            name="AccountState",
            fields=[
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="+",
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("session_version", models.PositiveIntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name="ExternalAccount",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("issuer", models.CharField(max_length=255)),
                ("subject", models.CharField(max_length=255)),
                ("provider", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="external_accounts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("issuer", "subject"),
                        name="rn_forge_auth_external_account",
                    )
                ],
            },
        ),
    ]
