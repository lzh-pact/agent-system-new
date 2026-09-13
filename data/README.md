# data 目录说明

本目录用于存放运行期数据，均在程序启动或演示时自动生成，无需手工创建：

- `chroma/` — ChromaDB 向量持久化目录（配置 `vector_backend=chroma` 时自动创建）；
- `checkpoints/` — 内容生成 Agent 的 Checkpointer 状态文件（自动创建）。

演示用的样例数据由 `demo.py:sample_records()` / `sample_knowledge()` 内联生成，
可通过 `frontend/app.py` 的「数据管道可视化」页上传自定义 CSV/JSON 进行测试。