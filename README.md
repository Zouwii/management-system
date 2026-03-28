# tb_tool_bt

- 后端：`cd backend && poetry install && poetry run python app.py` → http://127.0.0.1:5001  
- 前端开发：`cd frontend-vue && npm install && npm run dev`（Vite 默认 5173，`/api` 代理 5001）  
- 前端构建：`frontend-vue` 下 `npm run build`，产物在 `backend/static/vue/`，可只起后端用 5001 访问  
- HTTP API 前缀：`/api/bt`  
- 环境变量：`backend/.env.example`  

Docker：`./run-docker.sh`
