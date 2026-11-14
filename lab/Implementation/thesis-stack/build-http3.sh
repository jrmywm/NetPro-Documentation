#!/bin/bash
# Separate lab build; never replace /usr/bin/curl or its shared libraries.
set -euo pipefail
root="$HOME/netpro-thesis/http3"
mkdir -p "$root/src" "$root/prefix"
cd "$root/src"
for pair in nghttp3:v1.8.0 ngtcp2:v1.12.0; do
  name="${pair%%:*}"; tag="${pair#*:}"
  if [ ! -d "$name/.git" ]; then git clone --depth 1 --branch "$tag" "https://github.com/ngtcp2/$name.git" "$name"; fi
  test "$(git -C "$name" describe --tags --exact-match)" = "$tag"
  cd "$name"
  git submodule update --init --depth 1
  autoreconf -fi
  if [ "$name" = nghttp3 ]; then
    ./configure --prefix="$root/prefix" --enable-lib-only
  else
    PKG_CONFIG_PATH="$root/prefix/lib/pkgconfig" LDFLAGS="-Wl,-rpath,$root/prefix/lib" ./configure --prefix="$root/prefix" --enable-lib-only --with-gnutls --without-openssl
  fi
  make -j2
  make install
  cd "$root/src"
done
if [ ! -d curl/.git ]; then git clone --depth 1 --branch curl-8_13_0 https://github.com/curl/curl.git curl; fi
test "$(git -C curl describe --tags --exact-match)" = curl-8_13_0
cd curl
autoreconf -fi
PKG_CONFIG_PATH="$root/prefix/lib/pkgconfig" LDFLAGS="-Wl,-rpath,$root/prefix/lib" ./configure --prefix="$root/prefix" --with-gnutls --without-openssl --with-ngtcp2="$root/prefix" --with-nghttp3="$root/prefix" --disable-shared --enable-static --without-libpsl
make -j2
make install
"$root/prefix/bin/curl" -V
"$root/prefix/bin/curl" -V | grep -q 'HTTP3'
printf 'BUILD_HTTP3=PASS\n'
