<template>
  <img src="/maple-leaf-320.png" :width="size" :height="size" alt="Maple" draggable="false"
       style="object-fit: contain; display: block; transform: rotate(15deg)" />
</template>

<script setup>
defineProps({
  size: { type: Number, default: 34 },
})
</script>
