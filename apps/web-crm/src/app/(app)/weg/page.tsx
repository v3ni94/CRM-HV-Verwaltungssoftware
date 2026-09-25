import { redirect } from "next/navigation";

// WEG-Verwaltung ist in die Objekte integriert: die frühere WEG-Objektliste
// entspricht der Objektliste im Scope "hoa". Die Detailseiten unter
// /weg/[propertyId] bleiben bestehen und sind vom Objektdetail aus verlinkt.
export default function HoaPage() {
  redirect("/objekte?art=hoa");
}
