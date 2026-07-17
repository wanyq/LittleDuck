import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function App() {
  return (
    <main className="layout">
      <aside>
        <strong>LittleDuck Admin</strong>
        <span>LLM 配置</span>
        <span>聊天记录</span>
      </aside>
      <section>
        <p className="eyebrow">WI-001 工程骨架</p>
        <h1>PC 管理端独立入口</h1>
        <p>
          此页面只验证 /admin/ 构建路径和 1280 px 桌面布局边界。
          登录、配置、话题和调用详情由 WI-005 依据已接受合同实现。
        </p>
      </section>
    </main>
  );
}

const root = document.getElementById("root");
if (!root) {
  throw new Error("root element is missing");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>
);
