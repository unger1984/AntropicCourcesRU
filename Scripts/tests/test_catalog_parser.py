from pathlib import Path
import unittest

from export_anthropic_courses import extract_catalog_courses


FIXTURE = Path(__file__).parent / "fixtures" / "catalog.html"


class CatalogParserTest(unittest.TestCase):
    def test_extract_catalog_courses(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")

        courses = extract_catalog_courses(html)

        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0]["slug"], "claude-code-in-action")
        self.assertEqual(courses[1]["title"], "Claude 101")


if __name__ == "__main__":
    unittest.main()
