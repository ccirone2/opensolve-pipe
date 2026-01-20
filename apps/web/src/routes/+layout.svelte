<script lang="ts">
  import '../app.css';

  let { children } = $props();
</script>

<!-- Skip link for keyboard navigation -->
<a
  href="#main-content"
  class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-blue-600 focus:px-4 focus:py-2 focus:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
>
  Skip to main content
</a>

{@render children()}
