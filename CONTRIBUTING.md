# Contributing

Hampden County Mesh uses this repository as the working upstream deployment. Changes should keep HCM operational while avoiding hard-coded Discord IDs or tokens in source code.

For code changes:

1. Create a branch or fork.
2. Install `.[dev]`.
3. Run `ruff check .` and `pytest`.
4. Open a pull request describing the behavior change and any migration impact.

Other communities are expected to fork the repository and edit `config/hcm-sources.yml` and `.env`; generally useful fixes can be proposed back upstream with a pull request.
