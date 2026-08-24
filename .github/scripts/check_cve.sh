#!/bin/bash
# check_cve.sh - CVE-2026-43499 Detection Script

RTMUTEX="kernel/locking/rtmutex.c"
RTMUTEX_API="kernel/locking/rtmutex_api.c"

# Ensure required files exist
if [ ! -f "$RTMUTEX" ] || [ ! -f "$RTMUTEX_API" ]; then
    echo "Error: rtmutex source files not found. Run from kernel source root." >&2
    exit 1
fi

echo "========================================="
echo "CVE-2026-43499 Vulnerability Detection"
echo "========================================="
echo ""

# Primary fix
echo "[1] Primary fix (waiter_task local variable)"
if grep -Fq 'struct task_struct *waiter_task = waiter->task;' "$RTMUTEX"; then
    echo "    ✅ Fixed"
    PRIMARY=true
else
    echo "    ❌ Vulnerable: direct waiter->task usage"
    PRIMARY=false
fi
echo ""

# Null guard
echo "[2] Null pointer guard"
if grep -Fq 'if (!waiter_task) /* never enqueued */' "$RTMUTEX"; then
    echo "    ✅ Fixed"
    NULL_GUARD=true
else
    echo "    ❌ Missing null pointer guard"
    NULL_GUARD=false
fi
echo ""

# Proxy guard
echo "[3] Proxy error handling"
if grep -Fq 'if (unlikely(ret < 0))' "$RTMUTEX_API"; then
    echo "    ✅ Fixed"
    PROXY_GUARD=true
else
    echo "    ❌ Missing proxy error handling"
    PROXY_GUARD=false
fi
echo ""

# Summary
echo "========================================="
echo "Result:"
echo "========================================="

if $PRIMARY && $NULL_GUARD && $PROXY_GUARD; then
    echo "✅ Fully patched — no CVE-2026-43499 vulnerability"
    exit 0
elif ! $PRIMARY && ! $NULL_GUARD && ! $PROXY_GUARD; then
    echo "❌ Vulnerable — CVE-2026-43499 not patched"
    exit 1
else
    echo "⚠️  Inconsistent state detected:"
    echo "  Primary fix:      $($PRIMARY && echo '✅' || echo '❌')"
    echo "  Null guard:       $($NULL_GUARD && echo '✅' || echo '❌')"
    echo "  Proxy guard:      $($PROXY_GUARD && echo '✅' || echo '❌')"
    echo ""
    echo "Partial patch application detected. Manual inspection required."
    exit 2
fi
