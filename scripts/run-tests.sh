#!/usr/bin/env bash
# Pasang modul FoodTrace di database kosong lalu jalankan tes bertag `foodtrace`.
# Pemakaian: scripts/run-tests.sh [opsi odoo tambahan], mis. --db_host=db --db_user=odoo --db_password=odoo
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ODOO_BIN="${ODOO_BIN:-odoo}"
ODOO_ADDONS="${ODOO_ADDONS:-/usr/lib/python3/dist-packages/odoo/addons}"
DB="${TEST_DB:-foodtrace_test_$$}"
MODULES="foodtrace,foodtrace_mobile"
LOG="$(mktemp)"

"$ODOO_BIN" -d "$DB" -i "$MODULES" --addons-path="$ODOO_ADDONS,$ROOT/addons" \
  --test-enable --test-tags foodtrace --stop-after-init --without-demo=all \
  --log-level=info "$@" 2>&1 | tee "$LOG"

# Odoo tidak selalu keluar dengan kode gagal ketika tes gagal, jadi hasilnya dibaca dari log.
if grep -qE " (ERROR|CRITICAL) " "$LOG" || ! grep -qE " 0 failed, 0 error\(s\) of [1-9][0-9]* tests" "$LOG"; then
  echo "Tes FoodTrace GAGAL" >&2
  exit 1
fi
echo "Tes FoodTrace lulus"
