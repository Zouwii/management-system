## tb_tool_b1（超简易跑通版）

这个目录提供一个最小可运行的“前端页面 + Flask 后端”：

- 前端页面：展示后端返回的 JSON
- 后端接口：`POST /api/b1/proxy`（先 mock 钉钉响应，预留替换点）

### 运行方式

在 `tb_tool_b1/backend` 下安装依赖并启动后端：

```bash
cd tb_tool_b1/backend
poetry install --no-root
poetry run python app.py
```

浏览器打开：
- `http://127.0.0.1:5001/`

页面会自动请求一次接口，并把返回 JSON 展示出来。

