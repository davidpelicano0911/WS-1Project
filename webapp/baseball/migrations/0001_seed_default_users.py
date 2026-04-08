from django.contrib.auth.hashers import make_password
from django.db import migrations


DEFAULT_USERS = [
    {
        "username": "user",
        "email": "user@baseballix.local",
        "password": "password",
        "is_staff": False,
        "is_superuser": False,
    },
    {
        "username": "admin",
        "email": "admin@baseballix.local",
        "password": "password",
        "is_staff": True,
        "is_superuser": True,
    },
]


def seed_default_users(apps, schema_editor):
    user_model = apps.get_model("auth", "User")
    db_alias = schema_editor.connection.alias
    manager = user_model.objects.using(db_alias)

    manager.filter(username__in=["demo_user", "demo_admin"]).delete()

    for spec in DEFAULT_USERS:
        manager.update_or_create(
            username=spec["username"],
            defaults={
                "email": spec["email"],
                "password": make_password(spec["password"]),
                "is_active": True,
                "is_staff": spec["is_staff"],
                "is_superuser": spec["is_superuser"],
            },
        )


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(seed_default_users, migrations.RunPython.noop),
    ]
