import unittest

from app.services.contact_validation import normalize_email, normalize_phone


class EmailTest(unittest.TestCase):
    def test_valid_is_lowercased_and_trimmed(self):
        self.assertEqual(normalize_email("  Ali.Khan+x@Example.CO.uk "), "ali.khan+x@example.co.uk")

    def test_invalid(self):
        for bad in ["", "plain", "a@b", "a@b.c", "a b@example.com", "a@@example.com", "a@exa mple.com",
                    "a..b@example.com", "a@example..com", "a@example.com\nBcc: x@y.com", "@example.com",
                    "x" * 250 + "@example.com"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    normalize_email(bad)


class PhoneTest(unittest.TestCase):
    def test_valid(self):
        for ok in ["0300-1234567", "+92 300 1234567", "(415) 555-0132", "+1.415.555.0132"]:
            with self.subTest(ok=ok):
                self.assertEqual(normalize_phone(f"  {ok} "), ok)

    def test_invalid(self):
        for bad in ["", "abc", "12345", "1" * 16, "+92 300 123 45x67", "<script>"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    normalize_phone(bad)


if __name__ == "__main__":
    unittest.main()
