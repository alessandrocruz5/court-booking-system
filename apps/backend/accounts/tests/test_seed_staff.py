import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management import call_command, execute_from_command_line
from django.core.management.base import CommandError
from django.test import override_settings

from accounts.roles import Role, role_of

OWNER_EMAIL = "Owner@Example.com"
VIEWER_EMAIL = "viewer@example.com"
OWNER_PASSWORD = "owner-password-0123"
VIEWER_PASSWORD = "viewer-password-0123"


@pytest.fixture
def staff_env(monkeypatch):
    env = {
        "STAFF_OWNER_EMAIL": OWNER_EMAIL,
        "STAFF_OWNER_PASSWORD": OWNER_PASSWORD,
        "DEMO_VIEWER_EMAIL": VIEWER_EMAIL,
        "DEMO_VIEWER_PASSWORD": VIEWER_PASSWORD,
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return env


def _groups(user):
    return list(user.groups.values_list("name", flat=True))


def _sessions_of(user):
    return [
        s for s in Session.objects.all() if s.get_decoded().get("_auth_user_id") == str(user.pk)
    ]


@pytest.mark.django_db
def test_creates_both_accounts_with_one_role_and_no_flags(staff_env, capsys):
    call_command("seed_staff")

    owner = User.objects.get(username="owner@example.com")
    viewer = User.objects.get(username=VIEWER_EMAIL)
    assert owner.email == "owner@example.com"
    assert _groups(owner) == ["owner"]
    assert _groups(viewer) == ["viewer"]
    for user in (owner, viewer):
        assert user.is_active
        assert not user.is_staff
        assert not user.is_superuser
    assert owner.check_password(OWNER_PASSWORD)
    assert viewer.check_password(VIEWER_PASSWORD)

    out = capsys.readouterr().out
    assert "owner" in out
    assert "viewer" in out
    for secret in (OWNER_PASSWORD, VIEWER_PASSWORD, "owner@example.com", VIEWER_EMAIL):
        assert secret not in out.lower()


@pytest.mark.django_db
def test_rerun_rotates_password_resets_flags_and_signs_out_every_session(
    staff_env, monkeypatch, client
):
    call_command("seed_staff")
    viewer = User.objects.get(username=VIEWER_EMAIL)
    viewer.is_superuser = True
    viewer.save()
    assert client.login(username=VIEWER_EMAIL, password=VIEWER_PASSWORD)
    # Any other session goes too: only staff use Django sessions on this backend.
    other = User.objects.create_user(username="other@example.com", password="x" * 16)
    other_client = type(client)()
    other_client.force_login(other)
    assert len(_sessions_of(viewer)) == 1
    assert len(_sessions_of(other)) == 1

    monkeypatch.setenv("DEMO_VIEWER_PASSWORD", "a-brand-new-password-42")
    call_command("seed_staff")

    viewer.refresh_from_db()
    assert viewer.check_password("a-brand-new-password-42")
    assert not viewer.check_password(VIEWER_PASSWORD)
    assert not viewer.is_superuser
    assert not Session.objects.exists()
    assert User.objects.filter(username__in=["owner@example.com", VIEWER_EMAIL]).count() == 2


@pytest.mark.django_db
def test_rerun_deletes_sessions_signed_with_another_secret_key(staff_env, capsys):
    call_command("seed_staff")
    viewer = User.objects.get(username=VIEWER_EMAIL)
    # As in production: the server signs sessions with a key the laptop doesn't have.
    with override_settings(SECRET_KEY="the-cloud-run-secret-key-not-the-laptops-0123456789"):
        session = SessionStore()
        session["_auth_user_id"] = str(viewer.pk)
        session.create()
    assert Session.objects.get(pk=session.session_key).get_decoded() == {}
    capsys.readouterr()

    call_command("seed_staff")

    assert not Session.objects.filter(pk=session.session_key).exists()
    assert "Sessions signed out: 1" in capsys.readouterr().out


@pytest.mark.django_db
def test_rerun_moves_a_user_to_exactly_its_role(staff_env):
    call_command("seed_staff")
    owner = User.objects.get(username="owner@example.com")
    owner.groups.add(User.objects.get(username=VIEWER_EMAIL).groups.get())

    call_command("seed_staff")

    assert _groups(owner) == ["owner"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "email_var", "old_email", "password"),
    [
        (Role.OWNER, "STAFF_OWNER_EMAIL", "owner@example.com", OWNER_PASSWORD),
        (Role.VIEWER, "DEMO_VIEWER_EMAIL", VIEWER_EMAIL, VIEWER_PASSWORD),
    ],
)
def test_changed_email_deactivates_the_old_account(
    staff_env, monkeypatch, capsys, client, role, email_var, old_email, password
):
    call_command("seed_staff")
    monkeypatch.setenv(email_var, f"new-{role}@example.com")
    capsys.readouterr()

    call_command("seed_staff")

    old = User.objects.get(username=old_email)
    new = User.objects.get(username=f"new-{role}@example.com")
    assert not old.is_active
    assert _groups(old) == []
    assert role_of(old) is None
    assert authenticate(username=old_email, password=password) is None
    response = client.post("/dashboard/login/", {"email": old_email, "password": password})
    assert response["Location"] == "/dashboard/login/?error=invalid"
    assert new.is_active
    assert _groups(new) == [role]
    assert role_of(new) == role
    out = capsys.readouterr().out
    assert "Accounts deactivated: 1" in out
    assert "example.com" not in out.lower()


@pytest.mark.django_db
def test_rerun_with_the_same_emails_deactivates_nobody(staff_env, capsys):
    call_command("seed_staff")
    call_command("seed_staff")

    assert "Accounts deactivated: 0" in capsys.readouterr().out
    assert User.objects.filter(is_active=True).count() == 2


@pytest.mark.parametrize(
    "missing",
    ["STAFF_OWNER_EMAIL", "STAFF_OWNER_PASSWORD", "DEMO_VIEWER_EMAIL", "DEMO_VIEWER_PASSWORD"],
)
def test_missing_variable_exits_2_without_printing_a_password(
    staff_env, monkeypatch, capsys, missing
):
    monkeypatch.delenv(missing)

    with pytest.raises(SystemExit) as exc:
        execute_from_command_line(["manage.py", "seed_staff"])

    assert exc.value.code == 2
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert missing in output
    assert OWNER_PASSWORD not in output
    assert VIEWER_PASSWORD not in output


def test_empty_variable_counts_as_missing(staff_env, monkeypatch):
    monkeypatch.setenv("STAFF_OWNER_EMAIL", "  ")

    with pytest.raises(CommandError) as exc:
        call_command("seed_staff")

    assert exc.value.returncode == 2
    assert "STAFF_OWNER_EMAIL" in str(exc.value)


@pytest.mark.django_db
@pytest.mark.parametrize("variable", ["STAFF_OWNER_EMAIL", "DEMO_VIEWER_EMAIL"])
def test_invalid_email_exits_2_naming_only_the_variable(staff_env, monkeypatch, variable):
    monkeypatch.setenv(variable, "not-an-email@")

    with pytest.raises(CommandError) as exc:
        call_command("seed_staff")

    assert exc.value.returncode == 2
    assert variable in str(exc.value)
    assert "not-an-email" not in str(exc.value)
    assert not User.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("variable", ["STAFF_OWNER_PASSWORD", "DEMO_VIEWER_PASSWORD"])
def test_short_password_is_refused(staff_env, monkeypatch, variable):
    monkeypatch.setenv(variable, "fifteen-chars-x")

    with pytest.raises(CommandError) as exc:
        call_command("seed_staff")

    assert exc.value.returncode == 2
    assert variable in str(exc.value)
    assert "fifteen-chars-x" not in str(exc.value)
    assert not User.objects.exists()


@pytest.mark.django_db
def test_same_email_for_both_roles_is_refused(staff_env, monkeypatch):
    monkeypatch.setenv("DEMO_VIEWER_EMAIL", OWNER_EMAIL.upper())

    with pytest.raises(CommandError) as exc:
        call_command("seed_staff")

    assert exc.value.returncode == 2
    assert not User.objects.exists()
