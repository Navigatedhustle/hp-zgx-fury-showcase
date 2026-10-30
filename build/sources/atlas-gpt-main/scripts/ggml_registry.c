/* MIT. Register the native CUDA plugin before the speech TTS engine loads.
   ASR explicitly initializes CUDA; the prebuilt TTS path only queries registry. */
#include <dlfcn.h>
#include <stdlib.h>
__attribute__((constructor)) static void atlas_register_backends(void) {
 const char *dir = getenv("ATLAS_GGML_PLUGIN_DIR");
 void (*load)(const char *) = (void (*)(const char *))dlsym(RTLD_DEFAULT,"ggml_backend_load_all_from_path");
 if (dir && load) load(dir);
}
