<template>
  <form class="article-edit" novalidate @submit.prevent="submit">
    <component :is="headingTag">{{ heading }}</component>
    <label>
      Заголовок
      <input v-model="form.title" type="text" name="title">
    </label>
    <label>
      Текст
      <textarea v-model="form.body" name="body" rows="16"></textarea>
    </label>
    <label>
      Почему эта тема (обоснование)
      <textarea v-model="form.rationale" name="rationale" rows="3"></textarea>
    </label>
    <fieldset class="article-edit-urls">
      <legend>Ссылки</legend>
      <p v-if="form.urls.length === 0" class="muted">Ссылок нет.</p>
      <div v-for="(link, index) in form.urls" :key="link.key" class="article-edit-url">
        <input v-model="link.value" type="url" placeholder="https://…" :aria-label="'Ссылка ' + (index + 1)">
        <button type="button" class="danger" :disabled="busy" @click="removeUrl(index)">Удалить</button>
      </div>
      <button type="button" class="secondary" :disabled="busy" @click="addUrl">Добавить ссылку</button>
    </fieldset>
    <p v-if="error" class="error article-error">{{ error }}</p>
    <div class="article-actions">
      <button
        type="submit"
        :class="{ 'is-busy': busy }"
        :disabled="busy"
      >Сохранить</button>
      <button type="button" class="secondary" :disabled="busy" @click="cancel">Отмена</button>
    </div>
  </form>
</template>

<script setup>
import { reactive } from "vue"

// Общая форма статьи: правка (ArticleView) и свой пост (RunView).
// Запрос к API делает родитель по событию submit; busy и error приходят от него.
const props = defineProps({
  heading: { type: String, required: true },
  headingTag: { type: String, default: "h1" },
  initial: { type: Object, default: null },
  busy: { type: Boolean, default: false },
  error: { type: String, default: "" },
})
const emit = defineEmits(["submit", "cancel"])

let urlKey = 0
const start = props.initial || {}
const startUrls = Array.isArray(start.source_urls) ? start.source_urls : []
const form = reactive({
  title: start.title || "",
  body: start.body || "",
  rationale: start.rationale || "",
  urls: startUrls
    .map((u) => String(u || "").trim())
    .filter(Boolean)
    .map((value) => ({ key: ++urlKey, value })),
})

function addUrl() {
  form.urls.push({ key: ++urlKey, value: "" })
}

function removeUrl(index) {
  form.urls.splice(index, 1)
}

function submit() {
  if (props.busy) return
  emit("submit", {
    title: form.title,
    body: form.body,
    rationale: form.rationale,
    source_urls: form.urls.map((link) => link.value),
  })
}

function cancel() {
  if (props.busy) return
  emit("cancel")
}
</script>
