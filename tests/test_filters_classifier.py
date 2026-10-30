from jobcompass.classifier import classify_it, has_strong_it_signal, is_it_native
from jobcompass.config import Config
from jobcompass.filters import classify_exclusion
from jobcompass.models import Company, ExclusionAction, ItClass, SizeClass


def _company(**kw):
    base = dict(id="x", name="Acme", country="IT")
    base.update(kw)
    return Company(**base)


def test_exclude_below_size_threshold():
    cfg = Config().filters
    c = _company(employees_approx="100", sector_codes=["62"])
    res = classify_exclusion(c, cfg)
    assert res.action == ExclusionAction.EXCLUDE
    assert res.rule == "below_threshold"


def test_exclude_tobacco_sector():
    cfg = Config().filters
    c = _company(sector_codes=["C12"], employees_approx="5000")
    res = classify_exclusion(c, cfg)
    assert res.action == ExclusionAction.EXCLUDE
    assert res.rule == "blocklist_sector"


def test_exclude_consulting():
    cfg = Config().filters
    c = _company(business_summary="We provide IT consulting and staffing services.",
                 employees_approx="2000")
    res = classify_exclusion(c, cfg)
    assert res.action == ExclusionAction.EXCLUDE
    assert res.rule == "consulting_staffing"


def test_exclude_startup():
    cfg = Config().filters
    c = _company(business_summary="An early stage seed startup.", employees_approx="20")
    res = classify_exclusion(c, cfg)
    assert res.action == ExclusionAction.EXCLUDE
    assert res.rule == "startup"


def test_keep_large_it_company():
    cfg = Config().filters
    c = _company(sector_codes=["62"], employees_approx="3000")
    res = classify_exclusion(c, cfg)
    assert res.action == ExclusionAction.KEEP


def test_is_it_native():
    assert is_it_native(_company(sector_codes=["62.01"]), ["62", "63"])
    assert not is_it_native(_company(sector_codes=["05"]), ["62", "63"])


def test_strong_signal_requires_ats_or_division():
    assert has_strong_it_signal(_company(ats_slug="eni")) is not None
    assert has_strong_it_signal(
        _company(business_summary="We lead digital transformation")) is None
    assert has_strong_it_signal(
        _company(business_summary="Our digital hub builds cloud platforms")) is not None


def test_it_adjacent_large_with_ats_kept():
    cfg = Config()
    c = _company(name="ENI", sector_codes=["06"], ats_slug="eni",
                 size_class=SizeClass.MULTINATIONAL)
    res = classify_it(c, cfg)
    assert res.action == ExclusionAction.KEEP
    assert c.it_class == ItClass.IT_ADJACENT
    assert c.it_signal


def test_it_adjacent_medium_excluded():
    cfg = Config()
    c = _company(sector_codes=["06"], ats_slug="co", size_class=SizeClass.MEDIUM)
    res = classify_it(c, cfg)
    assert res.action == ExclusionAction.EXCLUDE
    assert res.rule == "it_adjacent_too_small"


def test_it_adjacent_fintech_excluded():
    cfg = Config()
    c = _company(name="PayFast", business_summary="A fintech payments company",
                 sector_codes=["64"], ats_slug="payfast", size_class=SizeClass.LARGE)
    res = classify_it(c, cfg)
    assert res.action == ExclusionAction.EXCLUDE
    assert res.rule == "fintech_trading"


def test_non_it_without_signal_excluded():
    cfg = Config()
    c = _company(sector_codes=["06"], size_class=SizeClass.MULTINATIONAL)
    res = classify_it(c, cfg)
    assert res.action == ExclusionAction.EXCLUDE
    assert res.rule == "no_it_signal"
