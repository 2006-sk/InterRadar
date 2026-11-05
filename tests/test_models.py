import unittest
from datetime import date

from internradar.models import (DATA, HARDWARE, OTHER, SOFTWARE, Posting, categorize, clean, epoch_ms_to_date,
                                is_internship, iso_to_date, relative_to_date, text_date_to_date)


class InternshipFilterTest(unittest.TestCase):
    def test_real_internships_match(self):
        for title in [
            "Software Engineering Intern - 2027", "Data Analyst, Intern", "Winter 2027 Propulsion Engineer Co-op",
            "Research Internship (Winter 2027)", "NVIDIA 2027 Internships: Hardware ASIC Design",
            # Regression: these were dropped by an over-broad "recruit|coordinator" exclusion.
            "2027 Applied Science Internship - Canada, PhD Student Science Recruiting",
            "Area Manager Intern - Summer 2027 (California), University Recruiting",
            "2027 Facilities Coordinator Intern", "Sourcing Recruiter Intern – Summer 2027",
            # Non-English titles seen on these sites.
            "Praktikum im Bereich Logistik - Berlin - Start 2027", "Apprenti(e) Program Manager FRA",
            "Développeur Logiciels (Stagiaire), Backend (l'été 2027 - Montreal)",
            "Program Manager Working Student 2027",
        ]:
            with self.subTest(title=title):
                self.assertTrue(is_internship(title))

    def test_non_internships_rejected(self):
        for title in [
            "Senior Internal Auditor", "Director, International Tax Planning", "Engineering Manager, Cooperative Systems",
            "Staff Software Engineer - Database Engine Internals", "Jr. Software Development Engineer",
            "University Recruiter, Interns", "Internship Program Manager", "Campus Recruiter - Internships",
        ]:
            with self.subTest(title=title):
                self.assertFalse(is_internship(title))

    def test_source_flag_counts_even_without_intern_in_title(self):
        self.assertTrue(is_internship("Meritocracy Fellowship", source_says_intern=True))
        self.assertFalse(is_internship("Meritocracy Fellowship"))

    def test_jobs_about_interns_stay_excluded_even_if_flagged(self):
        self.assertFalse(is_internship("Internship Program Manager", source_says_intern=True))


class CategoryTest(unittest.TestCase):
    def test_categories(self):
        cases = {
            "Software Engineering Intern - 2027": SOFTWARE,
            "Cybersecurity Engineer (Summer Internship)": SOFTWARE,
            "IT Engineer Intern (Early Careers Summer 2027)": SOFTWARE,
            "Développeur Logiciels (Stagiaire), Backend": SOFTWARE,
            "Applied Scientist Intern": DATA,
            "Data Analyst, Intern": DATA,
            "Quantitative Trader (Summer Internship)": DATA,
            "Hardware Design Engineer Intern": HARDWARE,
            "Winter 2027 Mechanical Engineer Co-op": HARDWARE,
            "Project Engineer Intern": HARDWARE,
            # Weak words ("developer", "cloud", "security", "data") must not make these technical.
            "Business Developer Intern, Early Careers 2027": OTHER,
            "Program Manager Intern, AWS Cloud Logistics": OTHER,
            "Associate Engagement Manager Intern- National Security, AWS": OTHER,
            "Strategy and Operations MBA Intern, Data": OTHER,
            "Sales Engineer Intern": OTHER,
            "Finance Intern - Undergrad Summer 2027": OTHER,
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(categorize(title), expected)


class DateHelpersTest(unittest.TestCase):
    def test_iso_keeps_the_sources_own_date(self):
        self.assertEqual(iso_to_date("2026-09-03T23:32:53-04:00"), "2026-09-03")
        self.assertEqual(iso_to_date("2026-11-05T18:33:17.862Z"), "2026-11-05")
        self.assertEqual(iso_to_date("2026-08-14"), "2026-08-14")
        self.assertIsNone(iso_to_date(None))
        self.assertIsNone(iso_to_date("not a date"))

    def test_epoch_ms(self):
        self.assertEqual(epoch_ms_to_date(1778517108152), "2026-05-11")
        self.assertIsNone(epoch_ms_to_date(None))

    def test_text_date_with_double_space(self):
        self.assertEqual(text_date_to_date("November  5, 2026"), "2026-11-05")
        self.assertIsNone(text_date_to_date("yesterday"))

    def test_relative_workday_dates(self):
        today = date(2026, 11, 5)
        self.assertEqual(relative_to_date("Posted Today", today), "2026-11-05")
        self.assertEqual(relative_to_date("Posted Yesterday", today), "2026-11-04")
        self.assertEqual(relative_to_date("Posted 23 Days Ago", today), "2026-10-13")
        self.assertIsNone(relative_to_date("Posted 30+ Days Ago", today))

    def test_clean(self):
        self.assertEqual(clean("  Cohort 0 \n"), "Cohort 0")
        self.assertEqual(clean(None), "")


class PostingTest(unittest.TestCase):
    def test_key_is_company_plus_source_id(self):
        p = Posting("stripe", "Stripe", "greenhouse", "8194291", "Data Analyst, Intern", "Toronto", "https://x")
        self.assertEqual(p.key, "stripe:8194291")
        self.assertEqual(p.to_dict()["category"], DATA)


if __name__ == "__main__":
    unittest.main()
