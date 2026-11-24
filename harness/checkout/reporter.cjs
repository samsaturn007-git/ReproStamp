const { writeFileSync } = require('node:fs');
const { relative } = require('node:path');

module.exports = class ReproStampReporter {
  cases = [];
  errors = [];
  builds = new Set();

  onError(error) {
    this.errors.push(error.message);
  }

  onTestEnd(test, result) {
    const annotation = result.annotations.find(({ type }) => type === 'reprostamp.assertion');
    const assertion = annotation ? JSON.parse(annotation.description) : null;
    const applicationFrame = result.errors.map(({ stack }) => stack?.match(
      /https?:\/\/127\.0\.0\.1:4173\/(src\/[\w.@/-]+)(?:\?[^\s:)]*)?(:\d+(?::\d+)?)/,
    )).find(Boolean);
    const location = result.annotations.find(({ type }) => type === 'reprostamp.application-location');
    const build = result.annotations.find(({ type }) => type === 'reprostamp.browser');
    if (build) this.builds.add(build.description);
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
      application_location: location?.description ?? (applicationFrame ? applicationFrame[1] + applicationFrame[2] : null),
      artifacts,
      error: result.error?.message ?? null,
    });
  }

  onEnd({ status }) {
    writeFileSync('/evidence/report.json', JSON.stringify({
      status,
      cases: this.cases,
      errors: this.errors,
      builds: [...this.builds].map(value => JSON.parse(value)),
    }));
  }
};
