from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0011_passwordresetotp"),
    ]

    operations = [
        migrations.DeleteModel(
            name="PasswordResetOTP",
        ),
    ]
