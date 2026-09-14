<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentCopy, Search } from '@element-plus/icons-vue'
import api from '../api'
import SourceChunkCard from '../components/SourceChunkCard.vue'
import { fmtTime, store } from '../store/app'

const form = reactive({ title: '', content: '', source: '' })
const submitting = ref(false)
const loadingSample = ref(false)

const searchForm = reactive({ query: '', top_k: 5 })
const searching = ref(false)
const hits = ref(null)

async function submit() {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('请填写文档标题与内容')
    return
  }
  submitting.value = true
  try {
    const res = await api.ingest({ ...form })
    ElMessage.success(`已入库,切分为 ${res.chunks} 个切片`)
    Object.assign(form, { title: '', content: '', source: '' })
    await Promise.all([store.refreshKnowledge(), store.refreshStats()])
  } finally {
    submitting.value = false
  }
}

async function loadSample() {
  loadingSample.value = true
  try {
    const res = await api.ingestSample()
    await Promise.all([store.refreshKnowledge(), store.refreshStats()])
    ElMessage.success(`已载入 4 篇示例文档,共 ${res.total_chunks} 个切片`)
  } finally {
    loadingSample.value = false
  }
}

async function doSearch() {
  if (!searchForm.query.trim()) return
  searching.value = true
  try {
    hits.value = await api.search(searchForm.query, searchForm.top_k)
  } finally {
    searching.value = false
  }
}
</script>

<template>
  <div class="page knowledge">
    <div class="kb-grid">
      <!-- 入库表单 -->
      <section class="card card-pad">
        <h3 class="card-title">文档入库</h3>
        <p class="card-desc">滑动窗口切片(默认 512 / 重叠 64),双路写入 FTS5 与向量索引</p>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="文档标题">
            <el-input v-model="form.title" placeholder="如:智能门锁 S1 参数" maxlength="200" />
          </el-form-item>
          <el-form-item label="来源(可选)">
            <el-input v-model="form.source" placeholder="如:产品手册 / 官网 FAQ" maxlength="200" />
          </el-form-item>
          <el-form-item label="文档内容">
            <el-input
              v-model="form.content"
              type="textarea"
              :rows="8"
              placeholder="粘贴文档正文…"
            />
          </el-form-item>
          <div class="form-actions">
            <el-button type="primary" :loading="submitting" @click="submit">入库</el-button>
            <el-button :icon="DocumentCopy" :loading="loadingSample" @click="loadSample">
              一键载入示例知识库
            </el-button>
          </div>
        </el-form>
      </section>

      <!-- 已入库列表 -->
      <section class="card card-pad docs-card">
        <div class="docs-head">
          <h3 class="card-title">已入库文档</h3>
          <div class="docs-count">
            <span class="num">{{ store.knowledge.total_docs }}</span> 篇 ·
            <span class="num">{{ store.knowledge.total_chunks }}</span> 切片
          </div>
        </div>
        <p class="card-desc">
          登记表随服务进程存在;重启后 FTS 索引清空需重新入库,向量库(Chroma)本地持久化
        </p>
        <div class="docs-list">
          <div v-if="!store.knowledge.docs.length" class="docs-empty">
            暂无文档,左侧手动入库或一键载入示例
          </div>
          <div v-for="d in store.knowledge.docs" :key="d.doc_id" class="doc-item">
            <div class="doc-icon"><el-icon :size="15"><DocumentCopy /></el-icon></div>
            <div class="doc-info">
              <div class="doc-title">{{ d.title }}</div>
              <div class="doc-meta">{{ d.source }} · {{ fmtTime(d.created_at) }}</div>
            </div>
            <el-tag size="small" effect="plain" type="info">{{ d.chunks }} 切片</el-tag>
          </div>
        </div>
      </section>
    </div>

    <!-- 检索验证 -->
    <section class="card card-pad">
      <h3 class="card-title">检索验证</h3>
      <p class="card-desc">混合检索:FTS5 全文 + 向量双路召回,各自归一化后按权重融合排序</p>
      <div class="search-bar">
        <el-input
          v-model="searchForm.query"
          placeholder="输入查询,验证知识库召回效果…"
          clearable
          @keydown.enter="doSearch"
        />
        <el-input-number v-model="searchForm.top_k" :min="1" :max="20" />
        <el-button type="primary" :icon="Search" :loading="searching" @click="doSearch">
          检索
        </el-button>
      </div>

      <div v-if="hits === null" class="search-empty">入库后输入查询词,查看命中片段与融合得分</div>
      <div v-else-if="!hits.length" class="search-empty">未命中任何切片,试试其他关键词或先入库文档</div>
      <div v-else class="hits">
        <SourceChunkCard v-for="(c, i) in hits" :key="i" :chunk="c" show-scores />
      </div>
    </section>
  </div>
</template>

<style scoped>
.knowledge {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.kb-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: start;
}

.form-actions {
  display: flex;
  gap: 12px;
}

/* ---------- 文档列表 ---------- */
.docs-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.docs-head .card-title {
  margin-bottom: 0;
}

.docs-count {
  font-size: 12.5px;
  color: var(--text-3);
  margin-bottom: 4px;
}

.docs-count .num {
  color: #22d3ee;
  font-weight: 600;
  font-size: 14px;
}

.docs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 430px;
  overflow-y: auto;
}

.docs-empty {
  padding: 36px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-3);
  border: 1px dashed var(--border-hairline);
  border-radius: 10px;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 14px;
  border: 1px solid var(--border-hairline);
  border-radius: 10px;
  background: var(--bg-inset);
}

.doc-icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(64, 158, 255, 0.12);
  color: #79bbff;
  flex: none;
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-title {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  font-size: 11.5px;
  color: var(--text-3);
  margin-top: 2px;
}

/* ---------- 检索 ---------- */
.search-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.search-bar .el-input {
  flex: 1;
}

.search-empty {
  padding: 34px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-3);
  border: 1px dashed var(--border-hairline);
  border-radius: 10px;
}

.hits {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

@media (max-width: 1000px) {
  .kb-grid {
    grid-template-columns: 1fr;
  }
}
</style>
