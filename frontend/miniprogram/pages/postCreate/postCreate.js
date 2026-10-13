// 发帖：标题 + 正文 + 标签 + 最多 9 张图
const { request } = require('../../utils/request')
const { pickAndUpload } = require('../../utils/upload')
const { fullUrl } = require('../../utils/util')

const MAX_IMAGES = 9
const MAX_TITLE = 50
const MAX_CONTENT = 2000

Page({
  data: {
    title: '', content: '', tags: '',
    images: [],            // 已上传的 /static/ 相对地址，提交用
    shown: [],             // 绝对地址，渲染用
    maxImages: MAX_IMAGES,
    uploading: false,
    progress: '',
  },
  back() { wx.navigateBack() },
  onTitle(e) { this.setData({ title: e.detail.value }) },
  onContent(e) { this.setData({ content: e.detail.value }) },
  onTags(e) { this.setData({ tags: e.detail.value }) },

  async addImages() {
    if (this.data.uploading) return
    const remain = MAX_IMAGES - this.data.images.length
    if (remain <= 0) {
      wx.showToast({ title: '最多 ' + MAX_IMAGES + ' 张', icon: 'none' })
      return
    }
    this.setData({ uploading: true })
    try {
      const urls = await pickAndUpload(remain, (done, total) => {
        this.setData({ progress: total > 1 ? '上传中 ' + (done + 1) + '/' + total : '' })
      })
      if (urls.length) this._setImages(this.data.images.concat(urls))
    } finally {
      this.setData({ uploading: false, progress: '' })
    }
  },

  _setImages(images) {
    this.setData({ images, shown: images.map(fullUrl) })
  },

  removeImage(e) {
    const images = this.data.images.slice()
    images.splice(e.currentTarget.dataset.i, 1)
    this._setImages(images)
  },

  previewImage(e) {
    const i = e.currentTarget.dataset.i
    wx.previewImage({ current: this.data.shown[i], urls: this.data.shown })
  },

  async submitPost() {
    const { title, content, tags, images } = this.data
    if (!title.trim() || !content.trim()) {
      wx.showToast({ title: '请填写标题和内容', icon: 'none' })
      return
    }
    if (this.data.uploading) {
      wx.showToast({ title: '图片还在上传，稍等一下', icon: 'none' })
      return
    }
    try {
      await request('/posts', 'POST', {
        title: title.slice(0, MAX_TITLE),
        content: content.slice(0, MAX_CONTENT),
        tags,
        images,
      })
      wx.showToast({ title: '发布成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 1200)
    } catch (e) { console.error(e) }
  }
})
