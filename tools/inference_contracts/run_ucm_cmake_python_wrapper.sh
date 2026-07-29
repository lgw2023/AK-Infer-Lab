#!/usr/bin/env bash
set -euo pipefail

: "${UCM_REAL_CMAKE:?UCM_REAL_CMAKE is required}"
: "${UCM_BUILD_PYTHON:?UCM_BUILD_PYTHON is required}"

rewritten=()
rewrote_uppercase=0
has_modern_python=0
is_configure=1

for argument in "$@"; do
  case "${argument}" in
    --build|--install|--version|-E)
      is_configure=0
      ;;
    -DPYTHON_EXECUTABLE=*)
      rewritten+=("-DPython_EXECUTABLE=${UCM_BUILD_PYTHON}")
      rewrote_uppercase=1
      has_modern_python=1
      continue
      ;;
    -DPython_EXECUTABLE=*)
      rewritten+=("-DPython_EXECUTABLE=${UCM_BUILD_PYTHON}")
      has_modern_python=1
      continue
      ;;
  esac
  rewritten+=("${argument}")
done

if test "${is_configure}" -eq 1 && test "${has_modern_python}" -eq 0; then
  rewritten+=("-DPython_EXECUTABLE=${UCM_BUILD_PYTHON}")
fi

if test -n "${UCM_CMAKE_WRAPPER_LOG:-}"; then
  printf 'is_configure=%s rewrote_uppercase=%s python=%s real_cmake=%s\n' \
    "${is_configure}" "${rewrote_uppercase}" "${UCM_BUILD_PYTHON}" \
    "${UCM_REAL_CMAKE}" >> "${UCM_CMAKE_WRAPPER_LOG}"
fi

exec "${UCM_REAL_CMAKE}" "${rewritten[@]}"
