# .github/workflows/reddit_test.yml
name: Reddit Test
on:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: |
          pip install playwright requests
          python -m playwright install chromium
          python -m playwright install-deps chromium
      - env:
          REDDIT_USERNAME: ${{ secrets.REDDIT_USERNAME }}
          REDDIT_PASSWORD: ${{ secrets.REDDIT_PASSWORD }}
        run: python reddit_test.py
