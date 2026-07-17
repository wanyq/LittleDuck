#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../../../.." && pwd)
RUN="$ROOT/runs/WI-002/product-ui-designer"
SUPPORT="$RUN/supporting-files"

required_files="
$RUN/answer.md
$RUN/RUN.yaml
$SUPPORT/ux-ui-spec.md
$SUPPORT/copy-catalog.md
$SUPPORT/input-mapping.md
$SUPPORT/design-decisions.md
$SUPPORT/h5-visual-board.html
$SUPPORT/h5-visual-board.png
$SUPPORT/admin-visual-board.html
$SUPPORT/admin-visual-board.png
"

for file in $required_files; do
  test -s "$file" || { echo "FAIL missing-or-empty: $file"; exit 1; }
done

for input in \
  用户端UI/注册页.png 用户端UI/登录页.png 用户端UI/对话框.png \
  用户端UI/对话框-输入状态.png 用户端UI/侧边栏.png \
  管理端UI/管理后台-登陆页.png 管理端UI/管理后台-LLM配置页.png \
  管理端UI/管理后台-聊天记录list页.png 管理端UI/管理后台-聊天记录-聊天记录tab.png \
  管理端UI/管理后台-聊天记录-LLM调用详情.png 管理端UI/组件补充稿.png; do
  rg -Fq "页面UI稿/$input" "$SUPPORT/input-mapping.md" || { echo "FAIL unmapped-input: $input"; exit 1; }
done

for phrase in \
  "375–430" "软键盘" "安全区" "生成中" "已停止" "重试" \
  "管理员登录" "LLM 配置" "话题列表" "聊天记录" "LLM 调用详情" \
  "每页 20 条" "不补造 System Prompt"; do
  rg -Fq "$phrase" "$SUPPORT/ux-ui-spec.md" "$SUPPORT/design-decisions.md" || { echo "FAIL missing-rule: $phrase"; exit 1; }
done

rg -Fq "EXAMPLE_NOT_A_REAL_OPENAI_API_KEY_000000" "$SUPPORT/admin-visual-board.html"
if rg -n --glob '!validate-delivery.sh' 'BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{16,}' "$RUN"; then
  echo "FAIL credential-pattern-found"
  exit 1
fi

for html in "$SUPPORT/h5-visual-board.html" "$SUPPORT/admin-visual-board.html"; do
  rg -Fq '<!doctype html>' "$html"
  rg -Fq 'PRD' "$html"
done

if command -v sips >/dev/null 2>&1; then
  for png in "$SUPPORT/h5-visual-board.png" "$SUPPORT/admin-visual-board.png"; do
    width=$(sips -g pixelWidth "$png" | awk '/pixelWidth/ {print $2}')
    height=$(sips -g pixelHeight "$png" | awk '/pixelHeight/ {print $2}')
    test "$width" -ge 1600 || { echo "FAIL png-width: $png $width"; exit 1; }
    test "$height" -ge 2400 || { echo "FAIL png-height: $png $height"; exit 1; }
    echo "PASS png: $(basename "$png") ${width}x${height}"
  done
fi

echo "PASS 11 inputs mapped"
echo "PASS required state/rule coverage"
echo "PASS credential pattern scan"
echo "PASS delivery validation"
