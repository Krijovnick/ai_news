import { createRouter, createWebHistory } from "vue-router"
import WeeksView from "./views/WeeksView.vue"
import RunView from "./views/RunView.vue"
import ArticleView from "./views/ArticleView.vue"
import KeywordsView from "./views/KeywordsView.vue"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "weeks", component: WeeksView },
    { path: "/run/:id", name: "run", component: RunView },
    { path: "/article/:id", name: "article", component: ArticleView },
    { path: "/keywords", name: "keywords", component: KeywordsView },
  ],
})

export default router
