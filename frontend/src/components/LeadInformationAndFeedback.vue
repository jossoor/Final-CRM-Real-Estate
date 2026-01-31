<template>
  <div class="flex flex-col">
    <!-- Information Section with DataFields -->
    <div class="flex-shrink-0 px-3 sm:px-10">
      <DataFields
        :doctype="doctype"
        :docname="docname"
        @beforeSave="(data) => $emit('beforeSave', data)"
        @afterSave="(data) => $emit('afterSave', data)"
      />
    </div>

    <!-- Feedback Section -->
    <div class="flex-1 border-t bg-white flex flex-col">
      <div class="flex-1 px-3 sm:px-10 py-6">
        <!-- Header -->
        <div class="flex items-center gap-4 mb-6">
          <h2 class="text-xl font-semibold text-ink-gray-8">
            {{ __('Feedback') }}
          </h2>
          <button
            @click="showFeedbackModal = true"
            class="px-3 py-1.5 bg-[#1a1c2e] text-white text-xs font-semibold rounded hover:bg-gray-800 transition-colors flex items-center gap-1"
          >
            <span class="text-sm">+</span>
            {{ __('Add Feedback') }}
          </button>
        </div>

        <!-- Search and Filters -->
        <div class="flex items-center gap-3 mb-6 max-w-5xl">
          <div class="relative flex-1">
            <FeatherIcon name="search" class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-900" />
            <input
              v-model="searchQuery"
              type="text"
              :placeholder="__('Search Feedback')"
              class="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-md outline-none text-sm font-medium text-gray-900 bg-white placeholder:text-gray-900"
            />
          </div>
          <div class="relative flex items-center gap-3">
            <Dropdown :options="activityTypeOptions">
              <template #default="{ open }">
                <div class="w-56 px-4 py-2 border border-gray-200 rounded-md text-sm font-medium text-ink-gray-8 bg-white flex items-center justify-between cursor-pointer select-none">
                  <span>{{ selectedType === 'All' ? __('Filter By Feedback Type') : (selectedType === 'Comment' ? __('Feedback') : selectedType) }}</span>
                  <FeatherIcon name="chevron-down" class="h-4 w-4 text-ink-gray-8" />
                </div>
              </template>
            </Dropdown>
            <div class="text-sm font-bold text-ink-gray-8 whitespace-nowrap">
              {{ activities.length }} {{ __('Total') }}
            </div>
          </div>
        </div>

        <!-- Activity List -->
        <div v-if="loading" class="flex items-center justify-center py-12 text-gray-500">
          <LoadingIndicator class="h-6 w-6 mr-2" />
          {{ __('Loading...') }}
        </div>
        <div v-else-if="!filteredActivities.length" class="text-center py-12 text-gray-500">
          {{ __('No feedback entries yet') }}
        </div>
        <div v-else class="space-y-6 max-w-xl">
          <div
            v-for="activity in filteredActivities"
            :key="activity.name"
            class="border border-gray-200 rounded-lg p-5 bg-white shadow-sm"
          >
            <!-- Header: Icon + Type/Title -->
            <div class="flex items-start gap-3 mb-3">
              <div class="mt-1">
                <component :is="getActivityIcon(activity)" class="h-5 w-5 text-gray-600" />
              </div>
              <div class="flex-1">
                <div class="flex items-center justify-between gap-2 mb-1">
                  <span class="text-[10px] font-bold uppercase tracking-wider text-gray-700 border border-gray-300 px-2 py-0.5 rounded bg-gray-50">
                    {{ getParsedFeedback(activity).type }}
                  </span>
                  <div class="flex items-center gap-3">
                    <div v-if="getReminderForActivity(activity)" class="flex items-center gap-1 text-[11px] font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded animate-pulse">
                      <FeatherIcon name="bell" class="h-3 w-3" />
                      {{ formatDateTime(getReminderForActivity(activity).remind_at) }}
                    </div>
                    <span class="text-[11px] font-medium text-gray-400">
                      {{ formatDateTime(activity.creation) }}
                    </span>
                  </div>
                </div>
                <h3 v-if="getParsedFeedback(activity).title" class="text-[17px] font-semibold text-ink-gray-8 leading-tight">
                  {{ getParsedFeedback(activity).title }}
                </h3>
              </div>
            </div>
            
            <!-- Activity Content Box -->
            <div class="bg-[#f3f4f6] rounded-lg p-4 text-[15px] text-gray-700 leading-snug whitespace-pre-wrap">
              {{ stripHtml(activity.content || '') }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Feedback Modal -->
    <LeadCommentsDialog
      v-if="showFeedbackModal"
      v-model:show="showFeedbackModal"
      :doctype="doctype"
      :name="docname"
      @update:show="(val) => { showFeedbackModal = val; if (!val) loadActivities(); }"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Button, Dropdown, Badge, call, dayjs } from 'frappe-ui'
import { formatDate } from '@/utils'
import DataFields from '@/components/Activities/DataFields.vue'
import LoadingIndicator from '@/components/Icons/LoadingIndicator.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import WhatsAppIcon from '@/components/Icons/WhatsAppIcon.vue'
import AddressIcon from '@/components/Icons/AddressIcon.vue'
import DetailsIcon from '@/components/Icons/DetailsIcon.vue'
import LeadCommentsDialog from '@/components/LeadCommentsDialog.vue'

const props = defineProps({
  leadData: {
    type: Object,
    required: true,
  },
  doctype: {
    type: String,
    default: 'CRM Lead',
  },
  docname: {
    type: String,
    required: true,
  },
})

defineEmits(['beforeSave', 'afterSave'])

const loading = ref(false)
const activities = ref([])
const reminders = ref([])
const searchQuery = ref('')
const selectedType = ref('All')
const showFeedbackModal = ref(false)


const activityTypeOptions = [
  { label: 'All Types', onClick: () => { selectedType.value = 'All' } },
  { label: 'Feedback', onClick: () => { selectedType.value = 'Comment' } },
  { label: 'Task', onClick: () => { selectedType.value = 'Task' } },
  { label: 'Call', onClick: () => { selectedType.value = 'Call' } },
  { label: 'WhatsApp', onClick: () => { selectedType.value = 'WhatsApp' } },
  { label: 'Property Showing', onClick: () => { selectedType.value = 'Property Showing' } },
  { label: 'Office Visit', onClick: () => { selectedType.value = 'Office Visit' } },
  { label: 'Meeting', onClick: () => { selectedType.value = 'Meeting' } },
]

// Computed filtered activities
const filteredActivities = computed(() => {
  let list = activities.value

  // Type filter
  if (selectedType.value !== 'All') {
    list = list.filter(a => {
      const subject = a.subject || ''
      if (subject.includes(':::')) {
        const type = subject.split(':::')[0]
        return type === selectedType.value
      }
      return selectedType.value === 'Comment' // Default if no special type
    })
  }


  if (!searchQuery.value) return list
  
  const query = searchQuery.value.toLowerCase()
  return list.filter(activity => {
    // Also search in the title part of subject
    const subject = activity.subject || ''
    const content = stripHtml(activity.content || '').toLowerCase()
    
    let searchableText = content
    if (subject.includes(':::')) {
      const [type, title] = subject.split(':::')
      searchableText += ' ' + title.toLowerCase() + ' ' + type.toLowerCase()
    } else {
      searchableText += ' ' + subject.toLowerCase()
    }
    
    return searchableText.includes(query)
  })
})

// Helper functions
function stripHtml(html) {
  try {
    const div = document.createElement('div')
    div.innerHTML = html || ''
    return (div.textContent || div.innerText || '').trim()
  } catch {
    return html || ''
  }
}

function isDelayed(activity) {
  const flag = activity?.delayed
  return flag === 1 || flag === true || flag === '1' || flag === 'Yes'
}

function getActivityIcon(activity) {
  let type = activity.comment_type || 'Comment'
  const subject = activity.subject || ''
  
  if (subject.includes(':::')) {
    type = subject.split(':::')[0]
  }
  
  const lowSubject = subject.toLowerCase()
  if (type === 'Property Showing' || type === 'Office Visit' || lowSubject.includes('showing')) return AddressIcon
  if (type === 'Meeting') return DetailsIcon
  
  switch (type) {
    case 'Task':
      return TaskIcon
    case 'Call':
      return PhoneIcon
    case 'WhatsApp':
      return WhatsAppIcon
    default:
      return CommentIcon
  }
}

function getActivityTypeName(activity) {
  const parsed = getParsedFeedback(activity)
  return parsed.title || parsed.type
}

function getParsedFeedback(activity) {
  const subject = activity.subject || ''
  if (subject.includes(':::')) {
    const [type, title] = subject.split(':::')
    return { 
      type: type === 'Comment' ? 'Feedback' : type, 
      title: title || '' 
    }
  }
  return { 
    type: activity.comment_type === 'Comment' ? 'Feedback' : (activity.comment_type || 'Feedback'), 
    title: subject 
  }
}

function getReminderForActivity(activity) {
  return reminders.value.find(r => r.comment === activity.name)
}

function formatDateTime(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const options = {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }
  const timeOptions = {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  }
  const datePart = date.toLocaleDateString('en-US', options)
  const timePart = date.toLocaleTimeString('en-US', timeOptions)
  return `${datePart} — ${timePart}`
}

// Load activities (comments/feedback)
async function loadActivities() {
  loading.value = true
  try {
    // 1. Load Comments
    const res = await call('frappe.client.get_list', {
      doctype: 'Comment',
      fields: ['name', 'subject', 'content', 'owner', 'creation', 'comment_type'],
      filters: [
        ['Comment', 'reference_doctype', '=', props.doctype],
        ['Comment', 'reference_name', '=', props.docname],
        ['Comment', 'comment_type', '=', 'Comment']
      ],
      order_by: 'creation desc',
      limit_page_length: 100,
    })
    activities.value = Array.isArray(res?.message) ? res.message : (Array.isArray(res) ? res : [])

    // 2. Load Reminders using specialized API
    const remRes = await call('crm.api.reminders.list_for_doc', {
      doctype: props.doctype,
      name: props.docname,
    })
    reminders.value = Array.isArray(remRes?.message) ? remRes.message : (Array.isArray(remRes) ? remRes : [])
    
  } catch (e) {
    console.error('Error loading activities:', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadActivities()
})
</script>
