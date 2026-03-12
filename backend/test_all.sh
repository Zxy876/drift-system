#!/bin/bash
echo "======================================="
echo "     DriftSystem 0-1 Testing Tool"
echo "======================================="

BASE="http://127.0.0.1:8000"

echo "--- Test: Add Node ---"
curl -s -X POST "$BASE/tree/add?content=测试节点"
echo; echo

echo "--- Test: Tree State ---"
curl -s "$BASE/tree/state"
echo; echo

echo "--- Test: Backtrack ---"
curl -s -X POST "$BASE/tree/backtrack"
echo; echo

echo "--- Test: Breakpoint ---"
curl -s -X POST "$BASE/tree/breakpoint"
echo; echo

echo "--- Test: DSL ---"
curl -s -X POST "$BASE/dsl/run" \
    -H "Content-Type: application/json" \
    -d '{"script": "ADD 你好"}'
echo; echo

echo "--- Test: Hint (AI Assist) ---"
curl -s -X POST "$BASE/hint/get" \
    -H "Content-Type: application/json" \
    -d '{"context": "测试一下AI"}'
echo; echo

echo "======================================="
echo "     DriftSystem 0-1 Test Complete"
echo "======================================="