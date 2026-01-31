<script setup>
import { ref, watch } from 'vue'
import { Dialog, Button, Textarea, Spinner, Avatar, call, toast } from 'frappe-ui'

const props = defineProps({
  show: { type: Boolean, default: false },
  doctype: { type: String, default: 'CRM Lead' },
  name: { type: String, required: true },     // docname
  pageSize: { type: Number, default: 20 },
  // لو فتحناه بهدف تعديل تعليق معيّن
  editComment: { type: Object, default: null }, // { name, content }
})
const emit = defineEmits(['update:show'])

const loading = ref(false)
const sending = ref(false)
const savingEdit = ref(false)
const error = ref('')
const comments = ref([])
const cursor = ref(null)

const newContent = ref('')
const newTitle = ref('') // Title for new feedback
const newType = ref('Comment') // Default type
const editing = ref(null) // {name, content, subject, comment_type}

const typeOptions = [
  { label: 'Feedback', value: 'Comment' },
  { label: 'Task', value: 'Task' },
  { label: 'Call', value: 'Call' },
  { label: 'WhatsApp', value: 'WhatsApp' },
  { label: 'Property Showing', value: 'Property Showing' },
  { label: 'Office Visit', value: 'Office Visit' },
  { label: 'Meeting', value: 'Meeting' },
]

/** خيارات الريمايندر */
const addReminder = ref(true)
const reminderAtLocal = ref('') // YYYY-MM-DDTHH:mm
const reminderError = ref('')

function stripHtml (html='') {
  return String(html)
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
}

function isDelayedFlag(comment) {
  const flag = comment?.delayed
  return flag === 1 || flag === true || flag === '1' || flag === 'Yes'
}

watch(() => props.show, async (open) => {
  if (!open) return
  editing.value = props.editComment
    ? { name: props.editComment.name, content: stripHtml(props.editComment.content) }
    : null
  addReminder.value = true
  reminderAtLocal.value = ''
  reminderError.value = ''
  await resetAndLoad()
})

async function refreshDelayedState() {
  try {
    await call('crm.api.reminders.recalc_delayed_for_doc', {
      doctype: props.doctype,
      name: props.name,
    })
  } catch (e) {
    console.debug('recalc_delayed_for_doc failed', e)
  }
}

async function resetAndLoad() {
  comments.value = []
  cursor.value = null
  error.value = ''
  await refreshDelayedState()
  await fetchComments()
}

async function fetchComments() {
  loading.value = true
  try {
    const filters = [
      ['Comment','reference_doctype','=',props.doctype],
      ['Comment','reference_name','=',props.name],
      ['Comment','comment_type','=','Comment'],
    ]
    if (cursor.value) filters.push(['Comment','creation','<',cursor.value])

    const res = await call('frappe.client.get_list', {
      doctype: 'Comment',
      fields: ['name','comment_by','owner','subject','content','creation','delayed'],
      filters,
      order_by: 'creation desc',
      limit_page_length: props.pageSize,
    })
    const items = Array.isArray(res?.message) ? res.message : (Array.isArray(res) ? res : [])
    comments.value.push(...items)
    if (items.length) cursor.value = items[items.length-1].creation
  } catch (e) {
    error.value = e?.message || 'Failed to load FeedBacks'
  } finally {
    loading.value = false
  }
}

function toDate(localValue) {
  try {
    const [date, time] = (localValue || '').split('T')
    if (!date || !time) return null
    const [y, mo, d] = date.split('-').map(x => parseInt(x, 10))
    const [hh, mm] = time.split(':').map(x => parseInt(x, 10))
    return new Date(y, (mo || 1)-1, d, hh || 0, mm || 0, 0, 0)
  } catch {
    return null
  }
}
function toServerDatetime(localValue) {
  const dt = toDate(localValue)
  if (!dt) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())} ${pad(dt.getHours())}:${pad(dt.getMinutes())}:${pad(dt.getSeconds())}`
}

async function addComment() {
  if (!newContent.value.trim() || sending.value) return

  // تحقق الريمايندر (لو مفعل)
  if (addReminder.value) {
    if (!reminderAtLocal.value) {
      reminderError.value = __('Reminder time is required')
      return
    }
    const when = toDate(reminderAtLocal.value)
    if (!when || when.getTime() <= Date.now()) {
      reminderError.value = __('Reminder must be in the future')
      return
    }
  }
  reminderError.value = ''

  sending.value = true
  error.value = ''
  try {
    // 1) أنشئ الكومنت using frappe.client.insert
    const ins = await call('frappe.client.insert', {
      doc: {
        doctype: 'Comment',
        reference_doctype: props.doctype,
        reference_name: props.name,
        subject: `${newType.value}:::${newTitle.value.trim()}`,
        content: newContent.value,
        comment_type: 'Comment',
      },
    })
    const commentName = ins?.name || ins?.message?.name || null

    // 2) ربط الريمايندر (اختياري)
    if (addReminder.value) {
      const desc = stripHtml(newContent.value)
      await call('crm.api.reminders.add_reminder', {
        doctype: props.doctype,
        name: props.name,
        remind_at: toServerDatetime(reminderAtLocal.value),
        description: `Follow-up: "${desc.slice(0, 140)}${desc.length > 140 ? '…' : ''}"`,
        comment: commentName,
      })
      // 3) تنظيف delayed flags على كومنتاتي لنفس المستند
      try {
        await call('crm.api.reminders.clear_delayed_flags', {
          doctype: props.doctype,
          name: props.name,
        })
      } catch (_) {}
    }

    newContent.value = ''
    newTitle.value = ''
    newType.value = 'Comment'
    reminderAtLocal.value = ''
    addReminder.value = true

      await resetAndLoad()
    toast.success(__('FeedBack added'))
  } catch (e) {
    error.value = e?.messages?.[0] || e?.message || 'Failed to add FeedBack'
  } finally {
    sending.value = false
  }
}

function startEdit(c) {
  editing.value = { name: c.name, content: stripHtml(c.content), subject: c.subject || '' }
}

async function saveEdit() {
  if (!editing.value?.name || !editing.value.content?.trim()) return
  savingEdit.value = true
  try {
    await call('frappe.client.set_value', {
      doctype: 'Comment',
      name: editing.value.name,
      fieldname: { subject: editing.value.subject || '', content: editing.value.content },
      value: '',
    })
    editing.value = null
    await resetAndLoad()
    toast.success(__('FeedBack updated'))
  } catch (e) {
    error.value = e?.message || 'Failed to update FeedBack'
  } finally {
    savingEdit.value = false
  }
}
</script>

<template>
  <Dialog
    :modelValue="show"
    @update:modelValue="val => emit('update:show', val)"
    :options="{ size: 'lg' }"
  >
    <template #body-title>
      <h3 class="text-lg font-semibold">{{ __('FeedBack') }} – {{ name }}</h3>
    </template>

    <template #body-content>
      <div class="space-y-4">
        <!-- Edit box (اختياري) -->
        <div v-if="editing" class="rounded-xl border p-3">
          <div class="mb-2 text-sm font-medium">{{ __('Edit FeedBack') }}</div>
          <div class="mb-2">
            <label class="block text-xs text-ink-gray-6 mb-1">{{ __('Title (optional)') }}</label>
            <input
              v-model="editing.subject"
              type="text"
              class="w-full rounded border px-3 py-2 text-sm"
              :placeholder="__('Enter title...')"
            />
          </div>
          <Textarea v-model="editing.content" rows="3" />
          <div class="mt-2 flex items-center gap-2">
            <Button :loading="savingEdit" variant="solid" @click="saveEdit">{{ __('Save') }}</Button>
            <Button variant="subtle" @click="editing = null">{{ __('Cancel') }}</Button>
          </div>
        </div>

        <!-- Add new -->
        <div class="rounded-xl border p-3">
          <div class="mb-2 text-sm font-medium">{{ __('Add new FeedBack') }}</div>
          <div class="mb-2 grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-ink-gray-6 mb-1">{{ __('Title (optional)') }}</label>
              <input
                v-model="newTitle"
                type="text"
                class="w-full rounded border px-3 py-2 text-sm"
                :placeholder="__('Enter title...')"
              />
            </div>
            <div>
              <label class="block text-xs text-ink-gray-6 mb-1">{{ __('Type') }}</label>
              <select
                v-model="newType"
                class="w-full rounded border px-3 py-2 text-sm bg-white"
              >
                <option v-for="opt in typeOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </div>
          </div>
          <Textarea v-model="newContent" rows="3" placeholder="اكتب تعليقك..." />

          <!-- Reminder 옵션 -->
          <div class="mt-3 flex flex-col gap-1">
            <label class="inline-flex items-center gap-2 text-sm">
              <input type="checkbox" v-model="addReminder" />
              <span>{{ __('Add a reminder') }}</span>
            </label>

            <div v-if="addReminder" class="flex items-center gap-2">
              <input
                type="datetime-local"
                v-model="reminderAtLocal"
                required
                class="w-[260px] rounded border px-2 py-1 text-sm"
              />
              <span v-if="reminderError" class="text-xs text-red-600">{{ reminderError }}</span>
            </div>
          </div>

          <div class="mt-2 flex items-center gap-2">
            <Button :loading="sending" variant="solid" @click="addComment">{{ __('Add FeedBack') }}</Button>
            <span v-if="error" class="text-red-600 text-sm">{{ error }}</span>
          </div>
        </div>

        <!-- List -->
        <div class="space-y-3">
          <div v-if="loading && !comments.length" class="flex justify-center py-6">
            <Spinner />
          </div>

          <div v-for="c in comments" :key="c.name" class="rounded-xl border p-3 flex gap-3">
            <Avatar :label="c.comment_by?.[0] || c.owner?.[0] || '?'" />
            <div class="min-w-0 flex-1">
              <!-- Title if available -->
              <div v-if="c.subject" class="font-semibold text-base text-ink-gray-9 mb-1">
                {{ c.subject }}
              </div>
              <div class="flex items-center gap-2 text-sm text-ink-gray-8">
                <span class="font-medium">{{ c.comment_by || c.owner }}</span>
                <span>•</span>
                <time :datetime="c.creation">{{ new Date(c.creation).toLocaleString() }}</time>

                <label class="ml-2 inline-flex items-center gap-1 text-[11px]" :title="__('Delayed flag is read-only')">
                  <input
                    type="checkbox"
                    disabled
                    class="h-3.5 w-3.5 cursor-not-allowed accent-red-500"
                    :checked="isDelayedFlag(c)"
                  />
                  <span>{{ __('Delayed') }}</span>
                </label>

                <Button size="sm" variant="subtle" class="ml-auto" @click="startEdit(c)">{{ __('Edit') }}</Button>
              </div>
              <div class="mt-1 prose max-w-none" v-html="c.content"></div>
            </div>
          </div>

          <div v-if="!loading && !comments.length" class="text-sm text-ink-gray-7">
            {{ __('No FeedBacks yet') }}
          </div>

          <div v-if="comments.length" class="flex justify-center">
            <Button :loading="loading" variant="subtle" @click="fetchComments">{{ __('Load older') }}</Button>
          </div>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.prose :deep(p){ margin:0; }
</style>
