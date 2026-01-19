<template>
  <Dialog
    v-model="show"
    :options="{ title: __('Assign To'), size: 'xl' }"
    @close="() => (assignees = [...oldAssignees])"
  >
    <template #body-content>
      <Link
        class="form-control"
        value=""
        doctype="User"
        @change="(option) => addValue(option) && ($refs.input.value = '')"
        :placeholder="__('John Doe')"
        :filters="{
          name: ['in', allowedUserNames],
        }"
        :hideMe="true"
      >
        <template #target="{ togglePopover }">
          <div
            class="w-full min-h-12 flex flex-wrap items-center gap-1.5 p-1.5 pb-5 rounded-lg bg-surface-gray-2 cursor-text"
            @click.stop="togglePopover"
          >
            <Tooltip
              :text="assignee.name"
              v-for="assignee in assignees"
              :key="assignee.name"
              @click.stop
            >
              <div>
                <div
                  class="flex items-center text-sm text-ink-gray-6 border border-outline-gray-1 bg-surface-white rounded-full hover:bg-surface-white !p-0.5"
                  @click.stop
                >
                  <UserAvatar :user="assignee.name" size="sm" />
                  <div class="ml-1">{{ getUser(assignee.name).full_name }}</div>
                  <Button
                    variant="ghost"
                    class="rounded-full !size-4 m-1"
                    @click.stop="removeValue(assignee.name)"
                  >
                    <template #icon>
                      <FeatherIcon name="x" class="h-3 w-3 text-ink-gray-6" />
                    </template>
                  </Button>
                </div>
              </div>
            </Tooltip>
          </div>
        </template>
        <template #item-prefix="{ option }">
          <UserAvatar class="mr-2" :user="option.value" size="sm" />
        </template>
        <template #item-label="{ option }">
          <Tooltip :text="option.value">
            <div class="cursor-pointer text-ink-gray-9">
              {{ getUser(option.value).full_name }}
            </div>
          </Tooltip>
        </template>
      </Link>
    </template>
    <template #actions>
      <div class="flex justify-between items-center gap-2">
        <div><ErrorMessage :message="__(error)" /></div>
        <div class="flex items-center justify-end gap-2">
          <Button
            variant="subtle"
            :label="__('Cancel')"
            @click="
              () => {
                assignees = [...oldAssignees]
                show = false
              }
            "
          />
          <Button
            variant="solid"
            :label="__('Update')"
            @click="updateAssignees()"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import UserAvatar from '@/components/UserAvatar.vue'
import Link from '@/components/Controls/Link.vue'
import { usersStore } from '@/stores/users'
import { capture } from '@/telemetry'
import { Tooltip, call, toast } from 'frappe-ui'
import { ref, computed, onMounted, watch } from 'vue'

const props = defineProps({
  doc: {
    type: Object,
    default: null,
  },
  docs: {
    type: [Set, Array],
    default: () => new Set(),
  },
  doctype: {
    type: String,
    default: '',
  },
  allowedUsers: {
    type: Array,
    default: () => [],
  },
  clearExisting: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['reload'])

const show = defineModel()
const assignees = defineModel('assignees')
const oldAssignees = ref([])

const error = ref('')

const { users, getUser } = usersStore()

// Load allowed users from API
const loadedAllowedUsers = ref([])

async function loadAllowedUsers() {
  try {
    // For bulk assignment (docs), use first doc name if available, otherwise use empty string
    // The API should handle the permission check based on user role/team regardless of doc name
    let docname = props.doc?.name || ''
    const docsArray = props.docs instanceof Set ? Array.from(props.docs) : (Array.isArray(props.docs) ? props.docs : [])
    const docsSize = props.docs instanceof Set ? props.docs.size : (Array.isArray(props.docs) ? props.docs.length : 0)
    
    if (!docname && docsSize > 0) {
      const firstDoc = docsArray[0]
      // Extract name - handle both string names and object documents
      docname = typeof firstDoc === 'string' ? firstDoc : (firstDoc?.name || firstDoc || '')
    }
    
    const res = await call('crm.fcrm.permissions.assign_to.get_assignable_users', {
      doctype: props.doctype,
      name: docname || '',
    })
    
    // Handle response - it might be wrapped in message property
    const result = res?.message || res
    loadedAllowedUsers.value = Array.isArray(result) ? result : []
  } catch (err) {
    console.error('Failed to load assignable users:', err)
    // On error, use empty array - server will validate anyway
    loadedAllowedUsers.value = []
  }
}

// Load allowed users when modal opens
watch(show, (isOpen) => {
  if (isOpen) {
    loadAllowedUsers()
    
    // If clearExisting is true, reset assignees to empty
    if (props.clearExisting) {
      assignees.value = []
      oldAssignees.value = []
    } else {
      // Otherwise, sync oldAssignees with current assignees
      oldAssignees.value = [...assignees.value]
    }
  }
})

// Get list of allowed user names for filtering
const allowedUserNames = computed(() => {
  // Use provided allowedUsers prop first
  if (props.allowedUsers && props.allowedUsers.length > 0) {
    return props.allowedUsers.map((u) => u.name || u)
  }
  // Use loaded allowedUsers from API
  if (loadedAllowedUsers.value && loadedAllowedUsers.value.length > 0) {
    return loadedAllowedUsers.value.map((u) => u.name || u)
  }
  // Fallback to all CRM users if no allowedUsers provided (for backwards compatibility)
  return users.data.crmUsers?.map((user) => user.name) || []
})

const removeValue = (value) => {
  assignees.value = assignees.value.filter(
    (assignee) => assignee.name !== value,
  )
}

const owner = computed(() => {
  if (!props.doc) return ''
  if (props.doctype == 'CRM Lead') return props.doc.lead_owner
  return props.doc.deal_owner
})

const addValue = (value) => {
  error.value = ''
  let obj = {
    name: value,
    image: getUser(value).user_image,
    label: getUser(value).full_name,
  }
  if (!assignees.value.find((assignee) => assignee.name === value)) {
    assignees.value.push(obj)
  }
}

async function updateAssignees() {
  error.value = ''
  
  try {
    const removedAssignees = oldAssignees.value
      .filter(
        (assignee) => !assignees.value.find((a) => a.name === assignee.name),
      )
      .map((assignee) => assignee.name)

    const addedAssignees = assignees.value
      .filter(
        (assignee) => !oldAssignees.value.find((a) => a.name === assignee.name),
      )
      .map((assignee) => assignee.name)

    // Extract document names once for all operations - handle both string names and object documents
    let docNames = []
    // Handle both Set and Array
    const docsArray = props.docs instanceof Set ? Array.from(props.docs) : (Array.isArray(props.docs) ? props.docs : [])
    const docsSize = props.docs instanceof Set ? props.docs.size : (Array.isArray(props.docs) ? props.docs.length : 0)
    
    if (docsSize > 0) {
      docNames = docsArray.map((doc) => {
        let name = ''
        if (typeof doc === 'string') {
          name = doc
        } else if (doc && typeof doc === 'object') {
          name = doc.name || doc.id || doc.value || doc.docname
          if (typeof name !== 'string' && name && typeof name === 'object') {
            name = name.name || name.value || JSON.stringify(name)
          }
        }
        
        if (typeof name !== 'string') {
          name = String(name || '')
        }

        console.log('AssignmentModal: Mapped doc to string name:', { 
          original: doc, 
          mapped: name, 
          type: typeof name 
        })
        return name
      }).filter((name) => name && name.trim() !== '')

      console.log('AssignmentModal: Final extracted docNames:', docNames)
      
      if (docNames.length === 0) {
        console.error('AssignmentModal: No valid document names found', { 
          docs: docsArray, 
          docsSize: docsSize 
        })
        error.value = __('No valid document names found in selected items')
        return
      }
    } else {
      console.warn('AssignmentModal: props.docs is empty or undefined', { 
        docs: props.docs, 
        docsSize: docsSize 
      })
    }
    
    // If clearExisting flag is set (coming from Clear Assignment),
    // first clear all existing assignments, then assign new ones
    if (docsSize > 0 && props.clearExisting) {
      // Clear all existing assignments first
      await call('crm.api.doc.remove_multiple_assignments', {
        doctype: props.doctype,
        names: JSON.stringify(docNames),
        ignore_permissions: true,
      })
    } else if (removedAssignees.length) {
      // Remove specific assignees for single doc
      await call('crm.api.doc.remove_assignments', {
        doctype: props.doctype,
        name: props.doc.name,
        assignees: JSON.stringify(removedAssignees),
      })
    }

    if (addedAssignees.length) {
      if (docsSize > 0) {
        if (docNames.length === 0) {
          error.value = __('No valid document names found in selected items')
          console.error('AssignmentModal: Cannot assign - docNames is empty')
          return
        }
        
        capture('bulk_assign_to', { doctype: props.doctype })
        
        // Use the robust bulk assignment method from crm.api.doc
        await call('crm.api.doc.assign_without_rule', {
          doctype: props.doctype,
          names: JSON.stringify(docNames),
          assign_to: JSON.stringify(addedAssignees),
          description: '',
        })
        
        toast.success(__('Assigned successfully'))
        emit('reload')
      } else {
        if (!props.doc || !props.doc.name) {
          error.value = __('Document name is required')
          console.error('AssignmentModal: props.doc.name is missing', { doc: props.doc })
          return
        }
        capture('assign_to', { doctype: props.doctype })
        await call('crm.api.doc.assign_without_rule', {
          doctype: props.doctype,
          name: props.doc.name,
          assign_to: JSON.stringify(addedAssignees),
          description: '',
        })
        toast.success(__('Assigned successfully'))
      }
    } else if (docsSize > 0 && props.clearExisting) {
      // If no new assignees selected but we cleared assignments, still reload
      toast.success(__('Assignment cleared successfully'))
      emit('reload')
    }
    show.value = false
  } catch (err) {
    console.error('Error updating assignees:', err)
    let msg = __('Failed to update assignments')
    if (err) {
      msg = err.messages?.[0] || err.message || msg
      // If it's a string, use it
      if (typeof err === 'string') msg = err
    }
    error.value = msg
  }
}

onMounted(() => {
  oldAssignees.value = [...assignees.value]
})
</script>
