const api="/api/v1";let token=sessionStorage.getItem("pi_token");let conversationId=null;
const show=id=>{document.querySelectorAll(".view").forEach(x=>x.classList.add("hidden"));const el=document.getElementById(id);el.classList.remove("hidden");const heading=el.querySelector("h2");if(heading){heading.setAttribute("tabindex","-1");heading.focus()}};
const message=text=>document.getElementById("message").textContent=text;
async function request(path,body,auth=false,method="POST"){const res=await fetch(api+path,{method,headers:{"Content-Type":"application/json",...(auth?{Authorization:`Bearer ${token}`}:{})},...(method==="GET"?{}:{body:JSON.stringify(body||{})})});if(!res.ok)throw new Error((await res.json()).title||"Une erreur est survenue.");return res.status===204?null:res.json()}
document.querySelectorAll("[data-view]").forEach(x=>x.onclick=async()=>{message("");show(x.dataset.view);if(x.dataset.view==="chat")await openChat();if(x.dataset.view==="editprofile")await openEditProfile()});
document.getElementById("register").onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));try{await request("/auth/register",d);message("Compte créé. Connectez-vous pour continuer.");show("login")}catch(err){message(err.message)}};
document.getElementById("signin").onsubmit=async e=>{e.preventDefault();try{const d=await request("/auth/sessions",Object.fromEntries(new FormData(e.target)));token=d.access_token;sessionStorage.setItem("pi_token",token);await afterLogin()}catch(err){message(err.message)}};
async function afterLogin(){
  // Onboarding must only ever be shown once: onboarding_completed_at is
  // stamped server-side on the very first profile save (see auth.py) and
  // never cleared afterwards, so it's a reliable signal a returning patient
  // shouldn't have to re-enter their name and re-tick consent boxes again.
  try{
    const profile=await request("/profile",null,true,"GET");
    if(profile.onboarding_completed_at){document.getElementById("hello").textContent=`Bonjour, ${profile.display_name||""}.`;show("home");return}
  }catch(err){/* fall through to onboarding if the profile can't be read yet */}
  show("onboarding")
}
document.getElementById("profile").onsubmit=async e=>{e.preventDefault();const d=new FormData(e.target);try{await request("/profile",{display_name:d.get("display_name"),about_me:d.get("about_me")||""},true);await request("/consents",{purpose:"CARE",version:"1"},true);if(d.get("learning"))await request("/consents",{purpose:"LEARNING",version:"1"},true);document.getElementById("hello").textContent=`Bonjour, ${d.get("display_name")}.`;show("home")}catch(err){message(err.message)}};
async function openEditProfile(){try{const profile=await request("/profile",null,true,"GET");const form=document.getElementById("edit-profile-form");form.display_name.value=profile.display_name||"";form.about_me.value=profile.about_me||""}catch(err){message(err.message)}}
document.getElementById("edit-profile-form").onsubmit=async e=>{e.preventDefault();const d=new FormData(e.target);try{await request("/profile",{display_name:d.get("display_name"),about_me:d.get("about_me")||""},true);document.getElementById("hello").textContent=`Bonjour, ${d.get("display_name")}.`;message("Profil mis à jour.");show("home")}catch(err){message(err.message)}};
document.getElementById("delete").onclick=async()=>{try{await request("/privacy/deletion-requests",{},true);message("Votre demande de suppression a été enregistrée.")}catch(err){message(err.message)}};
document.getElementById("logout").onclick=async()=>{try{await request("/auth/logout",{},true)}finally{sessionStorage.removeItem("pi_token");token=null;show("login")}};

function renderMessage(item){const el=document.createElement("p");el.className=`bubble ${item.author_type.toLowerCase()}`;el.textContent=item.content;return el}
async function openChat(){try{const convo=await request("/conversations",{},true);conversationId=convo.id;const history=await request(`/conversations/${conversationId}/messages`,null,true,"GET");const list=document.getElementById("messages");list.innerHTML="";history.items.forEach(item=>list.appendChild(renderMessage(item)));list.scrollTop=list.scrollHeight}catch(err){message(err.message)}}
document.getElementById("send-message").onsubmit=async e=>{
  e.preventDefault();
  const textarea=document.getElementById("message-text");
  const text=textarea.value.trim();
  if(!text)return;
  const form=e.target,button=form.querySelector("button"),waiting=document.getElementById("waiting");
  // The generative responder can take up to a couple of minutes (see the
  // notice above the conversation) -- without this, the UI just sits still
  // with no feedback, which reads as broken rather than slow.
  button.disabled=true;waiting.classList.remove("hidden");
  try{
    const result=await request(`/conversations/${conversationId}/messages`,{text},true);
    const list=document.getElementById("messages");
    list.appendChild(renderMessage(result.patient_message));
    list.appendChild(renderMessage(result.assistant_message));
    list.scrollTop=list.scrollHeight;
    textarea.value=""
  }catch(err){message(err.message)}
  finally{button.disabled=false;waiting.classList.add("hidden")}
};
