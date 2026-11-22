const { writeFileSync } = require('node:fs');
const { relative } = require('node:path');

module.exports = class ReproStampReporter {
  cases = [];
  errors = [];

  onError(error) {
    this.errors.push(error.message);
  }

  onTestEnd(test, result) {
    const annotation = result.annotations.find(({ type }) => type === 'reprostamp.assertion');
    const assertion = annotation ? JSON.parse(annotation.description) : null;
    const artifacts = {};
    for (const { name, path } of result.attachments) {
      if (path && (name === 'screenshot' || name === 'trace')) {
        artifacts[name] = relative('/evidence', path);
      }
    }

    this.cases.push({
      case_id: test.title,
      status: result.status,
      duration_ms: result.duration,
      assertion,
      artifacts,
      error: result.error?.message ?? null,
    });
  }

  onEnd({ status }) {
    writeFileSync('/evidence/report.json', JSON.stringify({
      status,
      cases: this.cases,
      errors: this.errors,
    }));
  }
};
