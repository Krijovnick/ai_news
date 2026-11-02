<template>
  <p v-if="notFound">Прогон не найден</p>
  <template v-else-if="run">
    <p><router-link to="/">← К неделям</router-link></p>
    <h1>Прогон #{{ run.id }}</h1>
    <p>
      Статус: <strong :class="'status-' + run.status">{{ run.status }}</strong><br>
      Начало: {{ run.started_at }}<br>
      Конец: {{ run.finished_at || "—" }}<br>
      Lookback: {{ run.lookback_days }} дн.<br>
      Telegram: {{ run.telegram_sent ? "отправлено" : "нет" }}
    </p>

    <template v-if="run.error_text">
      <h2>Протокол ошибок / пометок</h2>
      <div class="protocol">{{ run.error_text }}</div>
    </template>

    <h2>Разбор</h2>
    <div v-if="summary" class="summary">{{ summary }}</div>
    <p v-else class="muted">Разбора нет.</p>

    <h2>Статьи</h2>
    <ul v-if="articles.length">
      <li v-for="article in articles" :key="article.id">
        <router-link :to="'/article/' + article.id">{{ article.title }}</router-link>
      </li>
    </ul>
    <p v-else class="muted">Статей нет.</p>

    <ArticleForm
      v-if="adding"
      heading="Новый пост"
      heading-tag="h2"
      :busy="saving"
      :error="addError"
      @submit="createArticle"
      @cancel="cancelAdd"
    />
    <div v-else class="article-actions">
      <button type="button" @click="startAdd">Добавить пост</button>
    </div>
  </template>

  <div v-if="toastVisible" class="kw-toast" role="status">
    <span>{{ toastText }}</span>
    <button type="button" class="kw-toast-close" aria-label="Закрыть" @click="hideToast">×</button>
  </div>
</template>

<script setup>
import { ref, watch } from "vue"
import { useRoute } from "vue-router"
import ArticleForm from "../components/ArticleForm.vue"
import { readJson } from "../api.js"
import { useToast } from "../useToast.js"

const route = useRoute()
const run = ref(null)
const summary = ref("")
const articles = ref([])
const notFound = ref(false)
const adding = ref(false)
const saving = ref(false)
const addError = ref("")
const { toastText, toastVisible, showToast, hideToast } = useToast()

function startAdd() {
  addError.value = ""
  adding.value = true
}

function cancelAdd() {
  if (saving.value) return
  addError.value = ""
  adding.value = false
}

async function createArticle(payload) {
  if (saving.value) return
  saving.value = true
  try {
    const res = await fetch("/api/runs/" + run.value.id + "/articles", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
      body: JSON.stringify(payload),
    })
    const data = await readJson(res)
    if (res.status >= 400 || !data.ok) {
      addError.value = data.error || "Не удалось добавить пост"
      return
    }
    articles.value = [...articles.value, data.article]
    addError.value = ""
    adding.value = false
    showToast("Пост добавлен: " + data.article.title)
  } catch (err) {
    addError.value = "Ошибка запроса"
  } finally {
    saving.value = false
  }
}

async function load() {
  run.value = null
  summary.value = ""
  articles.value = []
  notFound.value = false
  adding.value = false
  addError.value = ""
  document.title = "AI News"
  try {
    const res = await fetch("/api/runs/" + route.params.id)
    const data = await res.json()
    if (res.status === 404 || !data.run) {
      notFound.value = true
      return
    }
    run.value = data.run
    summary.value = data.summary || ""
    articles.value = data.articles || []
    document.title = "Прогон #" + data.run.id + " — AI News"
  } catch (e) {
    notFound.value = true
  }
}

watch(() => route.params.id, load, { immediate: true })
</script>
