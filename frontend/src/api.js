// Тело ответа как JSON; не JSON — пустой объект.
export async function readJson(res) {
  try {
    return await res.json()
  } catch (err) {
    return {}
  }
}
