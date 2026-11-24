"""Local unit checks for task schema and normalization."""

import io
import tabnanny
import tokenize
import unittest
from pathlib import Path

from fastapi import HTTPException

from main import CONFIG, TaskInput, task_data


class TaskDataTests(unittest.TestCase):
    def test_default_status_and_normalized_title(self):
        result = task_data(TaskInput(title="  Write the release notes  "))
        self.assertEqual(result["title"], "Write the release notes")
        self.assertEqual(result["status"], CONFIG["statuses"][0])

    def test_unknown_status_is_rejected(self):
        with self.assertRaises(HTTPException) as failure:
            task_data(TaskInput(title="Write the release notes", status="?" * 33))
        self.assertEqual(failure.exception.status_code, 422)

    def test_python_whitespace(self):
        for filename in ("main.py", "test_app.py"):
            with self.subTest(filename=filename):
                text = Path(filename).read_text(encoding="utf-8")
                tabnanny.process_tokens(tokenize.generate_tokens(io.StringIO(text).readline))
                self.assertTrue(all(line == line.rstrip() for line in text.splitlines()))


if __name__ == "__main__":
    unittest.main()
