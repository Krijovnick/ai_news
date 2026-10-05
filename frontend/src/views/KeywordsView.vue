<template>
  <div id="keywords-root">
    <h1>Ключевые слова</h1>
    <p v-if="loadError" class="error">{{ loadError }}</p>
    <p v-if="actionError" class="error">{{ actionError }}</p>

    <template v-if="loaded && !loadError">
      <h2>Действующие (active)</h2>
      <form class="inline" style="margin-bottom:1rem" @submit.prevent="postKeyword('add_active', { phrase: newPhrase }, 'add_active')">
        <input v-model="newPhrase" type="text" name="phrase" placeholder="Новая фраза" required>
        <button
          type="submit"
          :class="{ 'is-busy': isBusy('add_active') }"
          :disabled="isBusy('add_active')"
        >Добавить</button>
      </form>
      <table>
        <thead><tr><th>Фраза</th><th>Действия</th></tr></thead>
        <tbody data-keywords="active">
          <tr v-if="active.length === 0" class="kw-empty">
            <td colspan="2" class="muted">Нет активных фраз</td>
          </tr>
          <tr v-for="kw in active" :key="kw.id" :data-id="kw.id">
            <td>
              <form class="inline" @submit.prevent="postKeyword('edit', { id: kw.id, phrase: kw.phrase }, 'edit-' + kw.id)">
                <input v-model="kw.phrase" type="text" name="phrase">
                <button
                  type="submit"
                  :class="{ 'is-busy': isBusy('edit-' + kw.id) }"
                  :disabled="isBusy('edit-' + kw.id)"
                >Сохранить</button>
              </form>
            </td>
            <td>
              <form @submit.prevent="postKeyword('delete', { id: kw.id }, 'delete-' + kw.id)">
                <button
                  type="submit"
                  class="danger"
                  :class="{ 'is-busy': isBusy('delete-' + kw.id) }"
                  :disabled="isBusy('delete-' + kw.id)"
                >Удалить</button>
              </form>
            </td>
          </tr>
        </tbody>
      </table>

      <h2>Предложенные (proposed)</h2>
      <table>
        <thead><tr><th>Фраза</th><th>Действия</th></tr></thead>
        <tbody data-keywords="proposed">
          <tr v-if="proposed.length === 0" class="kw-empty">
            <td colspan="2" class="muted">Нет предложений</td>
          </tr>
          <tr v-for="kw in proposed" :key="kw.id" :data-id="kw.id">
            <td>
              <form class="inline" @submit.prevent="postKeyword('edit_proposed', { id: kw.id, phrase: kw.phrase }, 'edit_proposed-' + kw.id)">
                <input v-model="kw.phrase" type="text" name="phrase">
                <button
                  type="submit"
                  class="secondary"
                  :class="{ 'is-busy': isBusy('edit_proposed-' + kw.id) }"
                  :disabled="isBusy('edit_proposed-' + kw.id)"
                >Поправить</button>
              </form>
              <div v-if="kw.run_id" class="muted">из прогона #{{ kw.run_id }}</div>
            </td>
            <td>
              <form style="display:inline" @submit.prevent="postKeyword('accept', { id: kw.id }, 'accept-' + kw.id)">
                <button
                  type="submit"
                  :class="{ 'is-busy': isBusy('accept-' + kw.id) }"
                  :disabled="isBusy('accept-' + kw.id)"
                >Принять</button>
              </form>
              <form style="display:inline" @submit.prevent="postKeyword('reject', { id: kw.id }, 'reject-' + kw.id)">
                <button
                  type="submit"
                  class="danger"
                  :class="{ 'is-busy': isBusy('reject-' + kw.id) }"
                  :disabled="isBusy('reject-' + kw.id)"
                >Отклонить</button>
              </form>
            </td>
          </tr>
        </tbody>
      </table>

      <details id="rejected-details">
        <summary>Отклонённые (<span id="rejected-count">{{ rejected.length }}</span>)</summary>
        <ul id="rejected-list">
          <li v-if="rejected.length === 0" class="muted kw-rejected-empty">Пусто</li>
          <li v-for="kw in rejected" :key="kw.id">{{ kw.phrase }}</li>
        </ul>
      </details>
    </template>

    <div v-if="toastVisible" id="kw-save-toast" class="kw-toast" role="status">
      <span>Фраза сохранена: {{ toastPhrase }}</span>
      <button type="button" class="kw-toast-close" aria-label="Закрыть" @click="hideSaveToast">×</button>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from "vue"

const active = ref([])
const proposed = ref([])
const rejected = ref([])
const newPhrase = ref("")
const loaded = ref(false)
const loadError = ref("")
const actionError = ref("")
const busyMap = reactive({})
const toastPhrase = ref("")
const toastVisible = ref(false)
let toastTimer = null

function isBusy(key) {
  return !!busyMap[key]
}

function showError(msg) {
  actionError.value = msg || "Ошибка"
}

function clearError() {
  actionError.value = ""
}

function hideSaveToast() {
  if (toastTimer) {
    clearTimeout(toastTimer)
    toastTimer = null
  }
  toastVisible.value = false
}

function showSaveToast(phrase) {
  hideSaveToast()
  toastPhrase.value = phrase || ""
  toastVisible.value = true
  toastTimer = setTimeout(hideSaveToast, 3500)
}

function phraseCompare(a, b) {
  return String(a || "").toLowerCase().localeCompare(String(b || "").toLowerCase())
}

function insertActiveSorted(item) {
  const phrase = item.phrase || ""
  const index = active.value.findIndex((row) => phraseCompare(phrase, row.phrase) < 0)
  if (index === -1) active.value.push(item)
  else active.value.splice(index, 0, item)
}

async function postKeyword(action, fields, busyKey) {
  if (busyMap[busyKey]) return
  if (action === "delete" && !confirm("Удалить?")) return

  busyMap[busyKey] = true
  try {
    const body = new FormData()
    body.set("action", action)
    if (fields.id != null && fields.id !== "") body.set("id", String(fields.id))
    if (fields.phrase != null) body.set("phrase", fields.phrase)

    const res = await fetch("/keywords", {
      method: "POST",
      body,
      headers: { "X-Requested-With": "fetch" },
    })
    let data = {}
    try {
      data = await res.json()
    } catch (err) {
      showError("Ошибка запроса")
      return
    }
    if (res.status >= 400 || !data.ok) {
      showError(data.error || "Ошибка")
      return
    }
    clearError()

    if (action === "add_active") {
      insertActiveSorted({
        id: data.id,
        phrase: data.phrase,
        status: "active",
        run_id: null,
      })
      newPhrase.value = ""
      return
    }

    if (action === "edit") {
      showSaveToast(data.phrase || "")
      const row = active.value.find((item) => item.id === data.id)
      if (row) row.phrase = data.phrase
      return
    }

    if (action === "edit_proposed") {
      const row = proposed.value.find((item) => item.id === data.id)
      if (row) row.phrase = data.phrase
      return
    }

    if (action === "delete") {
      active.value = active.value.filter((item) => item.id !== fields.id)
      return
    }

    if (action === "accept") {
      proposed.value = proposed.value.filter((item) => item.id !== data.id)
      insertActiveSorted({
        id: data.id,
        phrase: data.phrase,
        status: "active",
        run_id: null,
      })
      return
    }

    if (action === "reject") {
      proposed.value = proposed.value.filter((item) => item.id !== data.id)
      rejected.value.push({
        id: data.id,
        phrase: data.phrase || "",
        status: "rejected",
      })
    }
  } catch (err) {
    showError("Ошибка запроса")
  } finally {
    delete busyMap[busyKey]
  }
}

onMounted(async () => {
  document.title = "Ключевые слова — AI News"
  try {
    const res = await fetch("/api/keywords")
    if (!res.ok) {
      loadError.value = "Не удалось загрузить ключевые слова"
      return
    }
    const data = await res.json()
    active.value = data.active || []
    proposed.value = data.proposed || []
    rejected.value = data.rejected || []
  } catch (err) {
    loadError.value = "Не удалось загрузить ключевые слова"
  } finally {
    loaded.value = true
  }
})

onBeforeUnmount(() => {
  if (toastTimer) clearTimeout(toastTimer)
})
</script>
