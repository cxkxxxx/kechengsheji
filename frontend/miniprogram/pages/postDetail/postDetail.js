const { request } = require('../../utils/request')
Page({
  data: { post: {} },
  onLoad(options) { this.loadPost(options.id) },
  async loadPost(id) {
    try { this.setData({ post: await request('/posts/' + id) || {} }) }
    catch (e) { console.error(e) }
  }
})
