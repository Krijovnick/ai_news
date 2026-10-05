<template>
  <p v-if="notFound">Статья не найдена</p>
  <template v-else-if="article">
    <p><router-link :to="'/run/' + article.run_id">← К прогону #{{ article.run_id }}</router-link></p>
    <h1>{{ article.title }}</h1>
    <p v-if="article.rationale" class="muted">Почему эта тема: {{ article.rationale }}</p>
    <div class="article-body">{{ article.body }}</div>
  </template>
</template>

<script setup>
import { ref, watch } from "vue"
import { useRoute } from "vue-router"

const route = useRoute()
const article = ref(null)
const notFound = ref(false)

async function load() {
  article.value = null
  notFound.value = false
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
