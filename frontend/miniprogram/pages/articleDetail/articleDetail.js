// 文章详情逻辑
const { request } = require('../../utils/request')

Page({
  data: { article: {} },
  onLoad(options) { this.loadArticle(options.id) },
  async loadArticle(id) {
    try {
      const data = await request('/articles/' + id)
      this.setData({ article: data || {} })
    } catch (e) { console.error(e) }
  }
})
