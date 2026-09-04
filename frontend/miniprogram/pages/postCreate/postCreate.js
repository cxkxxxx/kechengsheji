// 发帖逻辑
const { request } = require('../../utils/request')

Page({
  data: { title: '', content: '', tags: '' },
  onTitle(e) { this.setData({ title: e.detail.value }) },
  onContent(e) { this.setData({ content: e.detail.value }) },
  onTags(e) { this.setData({ tags: e.detail.value }) },
  async submitPost() {
    if (!this.data.title || !this.data.content) {
      wx.showToast({ title: '请填写标题和内容', icon: 'none' })
      return
    }
    try {
      await request('/posts', 'POST', {
        title: this.data.title,
        content: this.data.content,
        tags: this.data.tags
      })
      wx.showToast({ title: '发布成功' })
      setTimeout(() => wx.navigateBack(), 1500)
    } catch (e) { console.error(e) }
  }
})
