<template>
  <p v-if="notFound">Статья не найдена</p>
  <template v-else-if="article">
    <p><router-link :to="'/run/' + article.run_id">← К прогону #{{ article.run_id }}</router-link></p>

    <template v-if="!editing">
      <h1>{{ article.title }}</h1>
      <p v-if="article.rationale" class="muted">Почему эта тема: {{ article.rationale }}</p>
      <div class="article-body">{{ article.body }}</div>
      <section v-if="sourceUrls.length" class="article-sources" aria-label="Использованные ссылки">
        <h2>Использованные ссылки</h2>
        <ul>
          <li v-for="(url, index) in sourceUrls" :key="index">
            <a :href="url" target="_blank" rel="noopener noreferrer">{{ url }}</a>
          </li>
        </ul>
      </section>
      <p v-if="actionError" class="error article-error">{{ actionError }}</p>
      <div class="article-actions">
        <button type="button" :disabled="deleting" @click="startEdit">Редактировать</button>
        <button
          type="button"
          class="danger"
          :class="{ 'is-busy': deleting }"
          :disabled="deleting"
          @click="deleteArticle"
        >Удалить пост</button>
      </div>
    </template>

    <ArticleForm
      v-else
      heading="Редактирование статьи"
      :initial="article"
      :busy="saving"
      :error="actionError"
      @submit="saveArticle"
      @cancel="cancelEdit"
    />
  </template>

  <div v-if="toastVisible" class="kw-toast" role="status">
    <span>{{ toastText }}</span>
    <button type="button" class="kw-toast-close" aria-label="Закрыть" @click="hideToast">×</button>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import ArticleForm from "../components/ArticleForm.vue"
import { readJson } from "../api.js"
import { useToast } from "../useToast.js"

const route = useRoute()
const router = useRouter()
const article = ref(null)
const notFound = ref(false)
const editing = ref(false)
const saving = ref(false)
const deleting = ref(false)
const actionError = ref("")
const { toastText, toastVisible, showToast, hideToast } = useToast()

const sourceUrls = computed(() => {
  const raw = article.value && article.value.source_urls
  if (!Array.isArray(raw)) return []
  return raw.map((u) => String(u || "").trim()).filter(Boolean)
})

function startEdit() {
  actionError.value = ""
  editing.value = true
}

function cancelEdit() {
  if (saving.value) return
  actionError.value = ""
  editing.value = false
}

async function saveArticle(payload) {
  if (saving.value) return
  saving.value = true
  try {
    const res = await fetch("/api/articles/" + article.value.id, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
      body: JSON.stringify(payload),
    })
    const data = await readJson(res)
    if (res.status >= 400 || !data.ok) {
      actionError.value = data.error || "Не удалось сохранить статью"
      return
    }
    article.value = data.article
    document.title = (data.article.title || "Статья") + " — AI News"
    actionError.value = ""
    editing.value = false
    showToast("Статья сохранена")
  } catch (err) {
    actionError.value = "Ошибка запроса"
  } finally {
    saving.value = false
  }
}

async function deleteArticle() {
  if (deleting.value) return
  if (!confirm("Удалить пост полностью? Это нельзя отменить.")) return
  deleting.value = true
  const runId = article.value.run_id
  try {
    const res = await fetch("/api/articles/" + article.value.id, {
      method: "DELETE",
      headers: { "X-Requested-With": "fetch" },
    })
    const data = await readJson(res)
    if (res.status >= 400 || !data.ok) {
      actionError.value = data.error || "Не удалось удалить статью"
      return
    }
    router.push("/run/" + runId)
  } catch (err) {
    actionError.value = "Ошибка запроса"
  } finally {
    deleting.value = false
  }
}

async function load() {
  article.value = null
  notFound.value = false
  editing.value = false
  actionError.value = ""
  document.title = "AI News"
  try {
    const res = await fetch("/api/articles/" + route.params.id)
    const data = await res.json()
    if (res.status === 404 || !data.article) {
      notFound.value = true
      return
    }
    article.value = data.article
    document.title = (data.article.title || "Статья") + " — AI News"
  } catch (e) {
    notFound.value = true
  }
}

watch(() => route.params.id, load, { immediate: true })
</script>
