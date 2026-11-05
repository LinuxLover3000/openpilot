#!/usr/bin/env bash
set -e

export SOURCE_DATE_EPOCH=0
export ZERO_AR_DATE=1

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"

ARCHNAME="${TARGET_ARCH:-}"
if [ -z "$ARCHNAME" ]; then
  ARCHNAME="x86_64"
  if [ -f /TICI ]; then
    ARCHNAME="larch64"
  fi
fi

case "$ARCHNAME" in
  x86_64)
    BLAS_TARGET="X64_AUTOMATIC"
    ;;
  larch64)
    BLAS_TARGET="ARMV8A_ARM_CORTEX_A57"
    ;;
  Darwin)
    BLAS_TARGET="ARMV8A_ARM_CORTEX_A57"
    ;;
  *)
    echo "Unsupported TARGET_ARCH: $ARCHNAME" >&2
    exit 1
    ;;
esac

ACADOS_FLAGS="-DACADOS_WITH_QPOASES=ON -UBLASFEO_TARGET -DBLASFEO_TARGET=$BLAS_TARGET"

if [[ "$OSTYPE" == "darwin"* ]]; then
  if [ -n "${TARGET_ARCH:-}" ] && [ "$ARCHNAME" != "Darwin" ]; then
    echo "TARGET_ARCH must be Darwin on macOS" >&2
    exit 1
  fi
  if [ "$(uname -m)" != "arm64" ]; then
    echo "Darwin builds must run on an ARM64 host" >&2
    exit 1
  fi
  ACADOS_FLAGS="$ACADOS_FLAGS -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_MACOSX_RPATH=1"
  ARCHNAME="Darwin"
elif [ "$ARCHNAME" = "Darwin" ]; then
  echo "Darwin builds must run on macOS" >&2
  exit 1
elif [ "$ARCHNAME" = "larch64" ] && [ "$(uname -m)" != "aarch64" ]; then
  echo "larch64 builds must run on an AArch64 host" >&2
  exit 1
elif [ "$ARCHNAME" = "x86_64" ] && [ "$(uname -m)" != "x86_64" ]; then
  echo "x86_64 builds must run on an x86_64 host" >&2
  exit 1
fi

if [ ! -d "$DIR/acados_repo" ]; then
  git clone https://github.com/acados/acados.git "$DIR/acados_repo"
  # git clone https://github.com/commaai/acados.git $DIR/acados_repo
fi
cd "$DIR/acados_repo"
git fetch --all
git checkout 51db6db146217e6624d7575f34e0421f28bc76a0 # acados main, 2026-10-29
git submodule update --depth=1 --recursive --init

# BLASFEO master includes the ARM CMake target-header path fix from issue #224.
# Remove this when acados updates blasfeo on main.
BLASFEO_COMMIT=38f790e2d49bfe3321da78ab5eefcaf37c7e1ead
git -C "$DIR/acados_repo/external/blasfeo" fetch --depth=1 origin "$BLASFEO_COMMIT"
git -C "$DIR/acados_repo/external/blasfeo" checkout "$BLASFEO_COMMIT"

# GCC 16 rejects the pointer-to-pointer arguments in qpOASES' copy helper.
# The constraints members are already Constraints *, matching ConstraintsCPY.
QPOASES_QPROBLEM="$DIR/acados_repo/external/qpoases/src/QProblem.c"
QPOASES_OLD="ConstraintsCPY( &(FROM->constraints),&(TO->constraints) );"
QPOASES_NEW="ConstraintsCPY(FROM->constraints, TO->constraints);"
if grep -Fq "$QPOASES_OLD" "$QPOASES_QPROBLEM"; then
  QPOASES_TMP=$(mktemp "${QPOASES_QPROBLEM}.XXXXXX")
  sed 's|ConstraintsCPY( &(FROM->constraints),&(TO->constraints) );|ConstraintsCPY(FROM->constraints, TO->constraints);|' \
    "$QPOASES_QPROBLEM" > "$QPOASES_TMP"
  mv "$QPOASES_TMP" "$QPOASES_QPROBLEM"
elif ! grep -Fq "$QPOASES_NEW" "$QPOASES_QPROBLEM"; then
  echo "Expected qpOASES source pattern not found in $QPOASES_QPROBLEM" >&2
  exit 1
fi

# build
rm -rf build
mkdir build
cd build
cmake $ACADOS_FLAGS ..
make -j"$(getconf _NPROCESSORS_ONLN)" install

INSTALL_DIR="$DIR/$ARCHNAME"
rm -rf $INSTALL_DIR
mkdir -p $INSTALL_DIR

rm -rf $DIR/include $DIR/acados_template
cp -r $DIR/acados_repo/include $DIR
cp -r $DIR/acados_repo/lib $INSTALL_DIR
cp -r $DIR/acados_repo/interfaces/acados_template/acados_template $DIR/
mkdir -p $DIR/lib
cp $DIR/acados_repo/lib/link_libs.json $DIR/lib/
#pip3 install -e $DIR/acados/interfaces/acados_template

# build tera
cd $DIR/acados_repo/interfaces/acados_template/tera_renderer/
if [[ "$OSTYPE" == "darwin"* ]]; then
  cargo build --verbose --release --target aarch64-apple-darwin
  cp target/aarch64-apple-darwin/release/t_renderer target/release/t_renderer
else
  cargo build --verbose --release
fi
cp target/release/t_renderer $INSTALL_DIR/
