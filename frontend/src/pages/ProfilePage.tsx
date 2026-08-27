import { KeyRound, Save, Trash2, Upload } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import { changePassword, removeAvatar, updateProfile, uploadAvatar } from "../api";
import { useAuth } from "../auth";
import { Avatar } from "../components/Avatar";

/** Meu perfil (Issue #56, DAP perfil-e-contato r1).
 *
 * **Dois cartões e dois botões de gravação, não um.** Trocar a senha e editar o nome são
 * transações diferentes: a primeira exige a senha atual e pode falhar por credencial, a segunda
 * não. Um "Salvar" único faria a troca de nome falhar por causa de um campo de senha que a pessoa
 * nem queria preencher.
 *
 * O feedback mora **dentro do cartão** que falhou ou teve sucesso, e não no topo da página: com
 * dois formulários independentes, um alerta no topo não diz qual dos dois falhou.
 *
 * O esqueleto de carregamento desenhado no board não existe aqui porque não tem como aparecer:
 * o dado vem de `/auth/me/`, que o `AuthProvider` já resolveu — `App` mostra o próprio spinner
 * enquanto `isLoading`, e `Layout` não renderiza sem usuário. Um estado inalcançável seria código
 * sem chamador, que este repositório trata como dívida e não como zelo. */
export function ProfilePage() {
  const { user, refreshUser } = useAuth();
  const [firstName, setFirstName] = useState(user?.first_name ?? "");
  const [lastName, setLastName] = useState(user?.last_name ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [profileError, setProfileError] = useState("");
  const [profileNotice, setProfileNotice] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordNotice, setPasswordNotice] = useState("");
  const [isUploading, setUploading] = useState(false);
  const [isSaving, setSaving] = useState(false);
  const [isChanging, setChanging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  if (!user) return null;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProfileError(""); setProfileNotice(""); setSaving(true);
    try {
      await updateProfile({ first_name: firstName, last_name: lastName });
      await refreshUser();
      setProfileNotice("Alterações salvas.");
    } catch (cause) { setProfileError((cause as Error).message); }
    finally { setSaving(false); }
  }

  // Sem conferência de tamanho ou tipo aqui de propósito. O `accept` abaixo é afordância nativa
  // do seletor; a **regra** é do servidor, e escrevê-la também em TypeScript criaria uma segunda
  // definição de "2 MB" que diverge da primeira em silêncio.
  async function sendPhoto(file: File) {
    setProfileError(""); setProfileNotice(""); setUploading(true);
    try {
      await uploadAvatar(file);
      await refreshUser();
      setProfileNotice("Foto atualizada.");
    } catch (cause) { setProfileError((cause as Error).message); }
    finally {
      setUploading(false);
      // Zerar o input é o que faz reenviar o **mesmo** arquivo disparar `change` de novo.
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function discardPhoto() {
    setProfileError(""); setProfileNotice(""); setUploading(true);
    try {
      await removeAvatar();
      await refreshUser();
      setProfileNotice("Foto removida.");
    } catch (cause) { setProfileError((cause as Error).message); }
    finally { setUploading(false); }
  }

  async function change(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError(""); setPasswordNotice(""); setChanging(true);
    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        new_password_confirm: newPasswordConfirm,
      });
      setPasswordNotice("Senha alterada.");
      setCurrentPassword(""); setNewPassword(""); setNewPasswordConfirm("");
    } catch (cause) { setPasswordError((cause as Error).message); }
    finally { setChanging(false); }
  }

  const displayName = user.first_name || user.username;

  return <section className="mx-auto grid max-w-2xl gap-5">
    <header className="page-head">
      <p className="eyebrow">Conta</p>
      <h1>Meu perfil</h1>
      <p>Seus dados de acesso ao Pulse. Só você vê e edita esta página.</p>
    </header>

    <form className="panel sm:p-6" aria-labelledby="perfil-foto-e-nome" onSubmit={event => void save(event)}>
      <div className="panel-heading"><h2 id="perfil-foto-e-nome">Foto e nome</h2></div>
      {profileError && <p role="alert" className="alert--error mb-4">{profileError}</p>}
      {profileNotice && <p role="status" className="alert--ok mb-4">{profileNotice}</p>}

      <div className="flex flex-wrap items-start gap-5">
        <Avatar user={user} name={displayName} size="lg" />
        <div className="grid min-w-[260px] flex-1 gap-3">
          <div className="flex flex-wrap gap-2.5">
            <button type="button" className="btn btn--secondary" disabled={isUploading} onClick={() => fileInput.current?.click()}>
              <Upload className="size-4" />{user.has_avatar ? "Trocar foto" : "Enviar foto"}
            </button>
            <button type="button" className="btn btn--secondary btn--secondary-danger" disabled={!user.has_avatar || isUploading} onClick={() => void discardPhoto()}>
              <Trash2 className="size-4" />Remover
            </button>
          </div>
          {/* Fora da tela mas alcançável por rótulo: o `<input type="file">` nativo não é
              estilizável e o board desenhou botões. `sr-only` e não `hidden`, senão nem o teclado
              nem o leitor de tela chegam nele. */}
          <label className="sr-only" htmlFor="perfil-arquivo">Arquivo da foto</label>
          <input
            id="perfil-arquivo" ref={fileInput} type="file" className="sr-only"
            accept="image/jpeg,image/png,image/webp"
            onChange={event => { const file = event.target.files?.[0]; if (file) void sendPhoto(file); }}
          />
          {isUploading
            ? <div className="upload-bar" role="progressbar" aria-label="Enviando foto" />
            : <p className="type-meta text-muted">JPG, PNG ou WebP, até 2 MB.</p>}
        </div>
      </div>

      <hr className="my-6 border-line" />

      <div className="form-grid">
        <label className="form-label">Nome<input className="field" value={firstName} onChange={event => setFirstName(event.target.value)} maxLength={150} /></label>
        <label className="form-label">Sobrenome<input className="field" value={lastName} onChange={event => setLastName(event.target.value)} maxLength={150} /></label>
      </div>
      <label className="form-label mt-4">E-mail<input className="field bg-surface-subtle text-muted" value={user.email} disabled /></label>
      <p className="type-meta mt-2 text-muted">O e-mail é a sua identidade de acesso e só um administrador pode alterá-lo.</p>

      <div className="mt-5 flex justify-end">
        <button className="btn" type="submit" disabled={isSaving}><Save className="size-4" />Salvar</button>
      </div>
    </form>

    <form className="panel sm:p-6" aria-labelledby="perfil-senha" onSubmit={event => void change(event)}>
      <div className="panel-heading"><h2 id="perfil-senha">Senha</h2></div>
      {passwordError && <p role="alert" className="alert--error mb-4">{passwordError}</p>}
      {passwordNotice && <p role="status" className="alert--ok mb-4">{passwordNotice}</p>}

      <div className="grid max-w-sm gap-4">
        <label className="form-label">Senha atual<input className="field" type="password" autoComplete="current-password" required value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} /></label>
        <label className="form-label">Nova senha<input className="field" type="password" autoComplete="new-password" required value={newPassword} onChange={event => setNewPassword(event.target.value)} /></label>
        <label className="form-label">Confirmar nova senha<input className="field" type="password" autoComplete="new-password" required value={newPasswordConfirm} onChange={event => setNewPasswordConfirm(event.target.value)} /></label>
      </div>
      <p className="type-meta mt-3 text-muted">A regra de força é a mesma já aplicada no convite.</p>

      <div className="mt-5 flex justify-end">
        <button className="btn" type="submit" disabled={isChanging}><KeyRound className="size-4" />Trocar senha</button>
      </div>
    </form>
  </section>;
}
