Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) {
  py -3 -m venv .venv
  & .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  pip install -r requirements.txt
} else {
  & .\.venv\Scripts\Activate.ps1
}
python -m alphaquest.app
