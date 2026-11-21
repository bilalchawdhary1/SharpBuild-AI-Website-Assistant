"""Production-readiness checks (core/preflight.py). Pure Python."""
import unittest
from types import SimpleNamespace as NS

from app.core.preflight import check, is_production, on_vercel

GOOD = dict(
    gemini_api_key="key", allowed_origins=["https://www.sharpbuild.io"], allowed_origin_regex="",
    database_url="postgresql+psycopg://u:p@db.example.com/app?sslmode=require",
    trust_forwarded_for=True, rate_limit_backend="database", enable_docs=False, log_format="json",
    admin_token="a" * 40, lead_webhook_url="https://crm.example.com/h", lead_webhook_secret="s",
    smtp_host="", lead_email_from="", lead_email_to="", generation_fallback_models="model-b", min_similarity=0.58,
)
VERCEL = {"VERCEL": "1", "VERCEL_ENV": "production"}


def settings(**over):
    return NS(**{**GOOD, **over})


def codes(findings, level=None):
    return sorted(f.code for f in findings if level in (None, f.level))


class EnvironmentTest(unittest.TestCase):
    def test_detects_production(self):
        self.assertTrue(is_production({"VERCEL_ENV": "production"}))
        self.assertTrue(is_production({"ENVIRONMENT": "Production"}))
        self.assertFalse(is_production({"VERCEL_ENV": "preview"}))
        self.assertFalse(is_production({}))
        self.assertTrue(on_vercel({"VERCEL": "1"}))
        self.assertFalse(on_vercel({}))


class ProductionTest(unittest.TestCase):
    def test_a_correct_production_setup_has_no_findings(self):
        self.assertEqual(check(settings(), VERCEL), [])

    def test_the_development_defaults_are_all_caught(self):
        dev = settings(gemini_api_key="", allowed_origins=["http://localhost:3000"], trust_forwarded_for=False,
                       database_url="postgresql+psycopg://u:p@localhost/app", rate_limit_backend="memory",
                       enable_docs=True, log_format="text", admin_token="", lead_webhook_url="", smtp_host="")
        found = check(dev, VERCEL)
        self.assertEqual(codes(found, "error"), ["database", "forwarded-for", "gemini-key", "origins"])
        self.assertEqual(codes(found, "warning"),
                         ["admin-token", "docs", "lead-channel", "log-format", "rate-limit"])

    def test_vercel_without_forwarded_for_is_an_error_because_everyone_shares_one_ip(self):
        found = check(settings(trust_forwarded_for=False), VERCEL)
        self.assertEqual(codes(found, "error"), ["forwarded-for"])
        self.assertIn("same IP", found[0].message)

    def test_forwarded_for_off_vercel_is_a_warning_to_check_the_proxy(self):
        found = check(settings(), {"ENVIRONMENT": "production"})
        self.assertEqual((codes(found, "error"), codes(found, "warning")), ([], ["forwarded-for"]))

    def test_origins(self):
        for bad in (["*"], ["http://www.sharpbuild.io"], ["https://ok.example", "http://localhost:3000"], []):
            with self.subTest(bad=bad):
                self.assertEqual(codes(check(settings(allowed_origins=bad), VERCEL), "error"), ["origins"])
        self.assertEqual(check(settings(allowed_origins=[], allowed_origin_regex=r"https://myapp-.*\.vercel\.app"), VERCEL), [])

    def test_database_ssl_warning(self):
        found = check(settings(database_url="postgresql+psycopg://u:p@db.example.com/app"), VERCEL)
        self.assertEqual(codes(found), ["database-ssl"])


class AlwaysOnTest(unittest.TestCase):
    """These break features everywhere, so they are reported outside production too."""

    def test_rules_apply_without_production(self):
        self.assertEqual(codes(check(settings(gemini_api_key=""), {}), "error"), ["gemini-key"])
        self.assertEqual(check(settings(allowed_origins=["http://localhost:3000"], enable_docs=True), {}), [])

    def test_half_configured_notifications_are_errors(self):
        self.assertEqual(codes(check(settings(lead_webhook_url="http://crm.example.com/h"), {}), "error"), ["webhook"])
        self.assertEqual(codes(check(settings(lead_webhook_secret=""), {}), "error"), ["webhook"])
        self.assertEqual(codes(check(settings(smtp_host="smtp.example.com"), {}), "error"), ["smtp"])
        self.assertEqual(check(settings(smtp_host="s", lead_email_from="a@b.co", lead_email_to="c@d.co"), {}), [])

    def test_origin_regex_must_not_match_strangers(self):
        for broad in (r".*", r"https://.*", r"https?://.*"):
            with self.subTest(broad=broad):
                self.assertEqual(codes(check(settings(allowed_origin_regex=broad), {}), "error"), ["origin-regex"])
        self.assertEqual(codes(check(settings(allowed_origin_regex="(unclosed"), {}), "error"), ["origin-regex"])
        self.assertEqual(check(settings(allowed_origin_regex=r"https://sharpbuild-[a-z0-9-]+\.vercel\.app"), {}), [])

    def test_weak_settings_are_warnings(self):
        found = check(settings(admin_token="short", generation_fallback_models=" ", min_similarity=0.1), {})
        self.assertEqual(codes(found, "warning"), ["admin-token", "fallback-model", "min-similarity"])
        self.assertEqual(codes(found, "error"), [])


if __name__ == "__main__":
    unittest.main()
