"""Django test runner that also writes a JUnit XML file for the CI report.

Used only by the CI pipeline:

    PYTHONPATH=.github/scripts python manage.py test --testrunner junit_runner.JUnitRunner

The file lands in ``$JUNIT_DIR`` (default ``test-results``) as ``junit.xml``. The console output
is the normal Django output; ``ci_report.py`` reads the XML and writes the job summary and the
annotations on failed tests.
"""

import os

from django.conf import settings
from xmlrunner.extra.djangotestrunner import XMLTestRunner


class JUnitRunner(XMLTestRunner):
    def __init__(self, *args, **kwargs):
        settings.TEST_OUTPUT_DIR = os.environ.get("JUNIT_DIR", "test-results")
        settings.TEST_OUTPUT_FILE_NAME = "junit.xml"
        settings.TEST_OUTPUT_VERBOSE = 1
        super().__init__(*args, **kwargs)
