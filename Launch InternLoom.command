#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  print "Python environment missing. Follow README.md setup steps."
  exit 1
fi
exec .venv/bin/python -m streamlit run app.py --browser.gatherUsageStats=false
