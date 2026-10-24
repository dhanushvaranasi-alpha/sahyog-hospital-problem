#!/usr/bin/env bash
# Downloads the five public datasets named in the engagement pack (p17) into data/raw/,
# plus each dataset's Kaggle metadata (title, licence) for the inventory.
# Run from the repo root, inside the project virtualenv:   bash data/fetch_datasets.sh
# Needs a Kaggle API token in ~/.kaggle/access_token (or KAGGLE_API_TOKEN), see README.
# data/raw/ is git-ignored: raw data never enters the repository.
# Set METADATA_ONLY=1 to refresh just the metadata files.
set -euo pipefail
cd "$(dirname "$0")"
RAW="raw"
mkdir -p "$RAW"

fetch() {  # fetch <kaggle owner/slug> <target folder>
  echo "==> $1"
  if [ "${METADATA_ONLY:-0}" != "1" ]; then
    kaggle datasets download "$1" -p "$RAW/$2" --unzip --force
  fi
  mkdir -p "$RAW/$2/_meta"
  kaggle datasets metadata "$1" -p "$RAW/$2/_meta"
}

fetch joniarroba/noshowappointments                 no_shows          # Medical Appointment No Shows (also OpenML 43439)
fetch itachi9604/disease-symptom-description-dataset disease_symptom
fetch tboyle10/medicaltranscriptions                 transcriptions
fetch shudhanshusingh/az-medicine-dataset-of-india   az_medicine
fetch prasad22/healthcare-dataset                    healthcare

if [ "${METADATA_ONLY:-0}" != "1" ]; then
  # Record exactly what was downloaded, so the inventory can cite checksums.
  ( cd "$RAW" && find . -type f ! -name MANIFEST.sha256 ! -path '*/_meta/*' -print0 | sort -z | xargs -0 shasum -a 256 > MANIFEST.sha256 )
  echo
  echo "Downloaded files:"
  ( cd "$RAW" && find . -type f ! -name MANIFEST.sha256 ! -path '*/_meta/*' -exec ls -lh {} \; | awk '{print $5, $9}' )
fi
echo
echo "Done."
