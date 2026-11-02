import { onBeforeUnmount, ref } from "vue"

// Короткое сообщение kw-toast: само исчезает, можно закрыть.
export function useToast(timeoutMs = 3500) {
  const toastText = ref("")
  const toastVisible = ref(false)
  let timer = null

  function hideToast() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    toastVisible.value = false
  }

  function showToast(text) {
    hideToast()
    toastText.value = text
    toastVisible.value = true
    timer = setTimeout(hideToast, timeoutMs)
  }

  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer)
  })

  return { toastText, toastVisible, showToast, hideToast }
}

