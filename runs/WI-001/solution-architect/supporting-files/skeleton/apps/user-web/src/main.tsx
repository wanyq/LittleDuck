import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function App() {
  return (
    <main className="shell">
      <section className="card">
        <div className="mark" aria-hidden="true">LD</div>
        <p className="eyebrow">WI-001 工程骨架</p>
        <h1>LittleDuck 用户端 H5</h1>
        <p>
          此页面只验证独立 H5 构建入口、移动端 viewport 与品牌方向。
          注册、登录、聊天和历史会话由 WI-004 依据已接受合同实现。
        </p>
        <ul>
          <li>目标宽度：375–430 CSS px</li>
          <li>API 命名空间：/api/v1/user</li>
          <li>Mock：pnpm mock</li>
        </ul>
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
