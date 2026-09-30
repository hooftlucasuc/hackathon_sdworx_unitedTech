"""company_id_for / caller_id_for: the agent may write the legal form with or without dots."""

import pytest

from app.pipeline import caller_id_for, company_id_for


@pytest.mark.parametrize(
    "name",
    [
        "Bakkerij Verhulst BV",
        "Bakkerij Verhulst B.V.",
        "Bakkerij Verhulst bv.",
        "bakkerij verhulst",
        "Bakkerij Verhulst BVBA",
        "Bakkerij Verhulst Comm.V.",
        "BV Bakkerij Verhulst",
        "B.V. Bakkerij Verhulst",
    ],
)
def test_legal_forms_are_dropped(name):
    assert company_id_for(name) == "bakkerij-verhulst"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Zorgcentrum De Linde v.z.w.", "zorgcentrum-de-linde"),
        ("Garage Van Damme N.V.", "garage-van-damme"),
        ("C.V.B.A. De Kring", "de-kring"),
        ("United Consulting", "united-consulting"),
        ("NV", "nv"),
        ("", None),
    ],
)
def test_company_ids(name, expected):
    assert company_id_for(name) == expected


def test_caller_id_includes_company_id():
    assert caller_id_for("Lindsey Tafels", company_id_for("United Consulting")) == "lindsey-tafels--united-consulting"
