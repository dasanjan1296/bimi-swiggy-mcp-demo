/**
 * Expo config plugin — patch Pods/fmt/include/fmt/base.h to force
 * FMT_USE_CONSTEVAL=0.
 *
 * Why this exists: Xcode 26 / Clang 17 enforce strict consteval rules and
 * reject `FMT_STRING(...)` calls with
 *   error: call to consteval function ... is not a constant expression
 * inside React Native's fmt-using pods. A compiler `-DFMT_USE_CONSTEVAL=0`
 * flag does NOT work because `base.h` itself redefines the macro. The fix
 * is a source-level patch applied during `pod install`.
 *
 * Why a config plugin: the patch needs to survive `expo prebuild --clean`,
 * which regenerates `ios/`. So we inject the patch into the generated
 * Podfile's `post_install` hook on every prebuild. Idempotent — re-running
 * prebuild won't stack copies.
 *
 * Maintenance: if a future Expo SDK changes the Podfile template's
 * closing structure, the regex anchor below will need to be updated.
 */
const { withDangerousMod } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const PATCH_MARKER = '# Bimi: fmt FMT_USE_CONSTEVAL=0 patch';

const PATCH_RUBY_BLOCK = `
    ${PATCH_MARKER} (Xcode 26 / Clang 17 strict consteval — see plugins/with-fmt-consteval-patch.js)
    fmt_base_h = File.expand_path('Pods/fmt/include/fmt/base.h', __dir__)
    if File.exist?(fmt_base_h)
      original = File.read(fmt_base_h)
      patched = original.gsub(
        /^#elif defined\\(__cpp_consteval\\)\\n#  define FMT_USE_CONSTEVAL 1$/,
        "#elif defined(__cpp_consteval)\\n#  define FMT_USE_CONSTEVAL 0"
      )
      if patched != original
        File.chmod(0644, fmt_base_h)
        File.write(fmt_base_h, patched)
        File.chmod(0444, fmt_base_h)
        Pod::UI.puts "Patched fmt/base.h: forced FMT_USE_CONSTEVAL=0 for Xcode 26"
      end
    end
`;

module.exports = function withFmtConstevalPatch(config) {
  return withDangerousMod(config, [
    'ios',
    async (cfg) => {
      const podfilePath = path.join(cfg.modRequest.platformProjectRoot, 'Podfile');
      let podfile = fs.readFileSync(podfilePath, 'utf8');

      if (podfile.includes(PATCH_MARKER)) {
        return cfg;
      }

      // Anchor on the final three-`end` close that wraps the resource-bundle
      // CODE_SIGNING_ALLOWED block, the post_install hook, and the target.
      // We insert the patch as the last statement inside post_install — i.e.
      // between the 4-space `end` (closing the each-loop) and the 2-space
      // `end` (closing post_install).
      const closingPattern = /(\n {4}end\n)( {2}end\nend\s*)$/;
      if (!closingPattern.test(podfile)) {
        throw new Error(
          '[with-fmt-consteval-patch] could not locate the post_install ' +
            'closing block in ios/Podfile. The Expo Podfile template may ' +
            'have changed — update plugins/with-fmt-consteval-patch.js.'
        );
      }
      podfile = podfile.replace(closingPattern, `$1${PATCH_RUBY_BLOCK}$2`);

      fs.writeFileSync(podfilePath, podfile);
      return cfg;
    },
  ]);
};
